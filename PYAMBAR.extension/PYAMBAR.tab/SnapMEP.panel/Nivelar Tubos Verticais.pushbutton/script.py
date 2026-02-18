# -*- coding: utf-8 -*-
"""
Nivelar Pro - Apruma tubos VERTICAIS usando conexoes como referencia.

LOGICA:
- Tubo com conexao inferior: usa XY do conector inferior como base
- Tubo com ambas conexoes: mantém inferior, move superior para mesmo XY
- Tubo sem conexao: usa ponto mais baixo (fallback)

VERSAO: 3.0
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Nivelar Tubos\nVerticais"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0"

import math

from Autodesk.Revit.DB import (
    BuiltInCategory, LocationCurve, Line, XYZ
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit

doc = revit.doc
uidoc = revit.uidoc


def get_id_val(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


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
    return dxy > 0.00001 and dz > 3.7 * dxy


def get_vertical_pipes():
    """Usa selecao ativa ou solicita selecao ao usuario."""
    selection = revit.get_selection()
    candidates = [
        doc.GetElement(eid) for eid in selection.element_ids
        if doc.GetElement(eid) and doc.GetElement(eid).Category
        and get_id_val(doc.GetElement(eid).Category.Id) == int(BuiltInCategory.OST_PipeCurves)
    ]
    if not candidates:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, "Selecione os tubos verticais")
            candidates = [
                doc.GetElement(r.ElementId) for r in refs
                if doc.GetElement(r.ElementId) and doc.GetElement(r.ElementId).Category
                and get_id_val(doc.GetElement(r.ElementId).Category.Id) == int(BuiltInCategory.OST_PipeCurves)
            ]
        except OperationCanceledException:
            return []
    return [p for p in candidates if is_nearly_vertical(p)]


def get_endpoint_connector(pipe, point, tolerance=0.1):
    """Retorna o conector mais proximo do ponto, ou None."""
    try:
        for conn in pipe.ConnectorManager.Connectors:
            if conn.Origin.DistanceTo(point) < tolerance:
                return conn
    except Exception:
        pass
    return None


def get_connected_ref(connector, pipe_id):
    """Retorna o conector do elemento vizinho (nao o proprio tubo)."""
    try:
        for ref in connector.AllRefs:
            if ref.Owner.Id != pipe_id:
                return ref
    except Exception:
        pass
    return None


def fix_vertical_smart(pipe):
    """Apruma tubo vertical mantendo conexao inferior.

    Estrategia: desconectar → corrigir curva → reconectar inferior.
    Usa p_bot exato para garantir que a posicao nao muda.
    """
    loc = pipe.Location
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)

    # Ordenar: bottom = Z menor, top = Z maior
    if p0.Z <= p1.Z:
        p_bot, p_top = p0, p1
    else:
        p_bot, p_top = p1, p0

    dxy = math.sqrt((p_top.X - p_bot.X) ** 2 + (p_top.Y - p_bot.Y) ** 2)
    if dxy < 0.00001:
        return False

    # Detectar conexoes e salvar referencia ao elemento vizinho
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

    # Corrigir: manter p_bot exato, alinhar top ao XY do bottom
    loc.Curve = Line.CreateBound(
        XYZ(p_bot.X, p_bot.Y, p_bot.Z),
        XYZ(p_bot.X, p_bot.Y, p_top.Z)
    )

    # Reconectar inferior: tubo bottom está no mesmo XY do fitting
    if bot_ref:
        new_conn_bot = get_endpoint_connector(pipe, p_bot)
        if new_conn_bot:
            try:
                new_conn_bot.ConnectTo(bot_ref)
            except Exception:
                pass

    return True


def main():
    pipes = get_vertical_pipes()
    if not pipes:
        return

    with revit.Transaction("Nivelar Tubos Verticais Pro"):
        for pipe in pipes:
            try:
                fix_vertical_smart(pipe)
            except Exception:
                pass


if __name__ == "__main__":
    main()
