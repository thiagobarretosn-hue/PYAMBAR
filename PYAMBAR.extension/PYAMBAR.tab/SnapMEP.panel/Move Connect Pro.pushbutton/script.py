# -*- coding: utf-8 -*-
"""
Move Connect Pro v1.0
Move, conecta e alinha automaticamente tubos verticais.

DIFERENCA DO "CONECTAR MOVENDO":
Apos conectar, se o elemento movido for um tubo quase vertical,
alinha automaticamente usando o conector conectado como referencia.
Tubos diagonais (30/45/60/90) nao sao afetados pelo filtro de angulo.

WORKFLOW:
1. Selecione o elemento ALVO (fixo)
2. Selecione o elemento a MOVER
3. Conecta + alinha se for tubo vertical

VERSAO: 1.0
AUTOR: Thiago Barreto Sobral Nunes
"""

__title__ = "Conectar\nMovendo Pro"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"
__persistentengine__ = True

# ============================================================================
# IMPORTS
# ============================================================================

import os
import sys
import math

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from Autodesk.Revit.DB import (
    BuiltInCategory, LocationCurve, Line, XYZ
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms

from Snippets._mep_connector_utils import (
    get_connector_manager,
    get_connector_closest_to,
    connect_elements,
    validate_connectors_compatible,
    MEPElementFilter
)

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc


def get_id_val(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


# ============================================================================
# ALINHAMENTO VERTICAL (logica Nivelar Pro)
# ============================================================================

def get_endpoint_connector(pipe, point, tolerance=0.1):
    try:
        for conn in pipe.ConnectorManager.Connectors:
            if conn.Origin.DistanceTo(point) < tolerance:
                return conn
    except Exception:
        pass
    return None


def get_connected_ref(connector, pipe_id):
    try:
        for ref in connector.AllRefs:
            if ref.Owner.Id != pipe_id:
                return ref
    except Exception:
        pass
    return None


def is_nearly_vertical(pipe):
    """Tubo quase vertical: angulo < 15 graus da vertical (dz > 3.7 * dxy).
    Exclui diagonais 30/45/60 graus.
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    dz = abs(p1.Z - p0.Z)
    dxy = math.sqrt((p1.X - p0.X) ** 2 + (p1.Y - p0.Y) ** 2)
    return dxy > 0.00001 and dz > 3.7 * dxy


def align_vertical_pipe(pipe, ref_connector):
    """Alinha tubo vertical usando o conector conectado como referencia XY.

    Estrategia: desconectar ambos → corrigir curva → reconectar.
    O conector ref_connector define o XY de referencia (posicao correta).
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)

    if p0.Z <= p1.Z:
        p_bot, p_top = p0, p1
    else:
        p_bot, p_top = p1, p0

    # Usar XY do conector de referencia (o que acabou de se conectar)
    ref_x = ref_connector.Origin.X
    ref_y = ref_connector.Origin.Y

    # Salvar referencias antes de desconectar
    conn_bot = get_endpoint_connector(pipe, p_bot)
    conn_top = get_endpoint_connector(pipe, p_top)

    bot_ref = get_connected_ref(conn_bot, pipe.Id) if (conn_bot and conn_bot.IsConnected) else None
    top_ref = get_connected_ref(conn_top, pipe.Id) if (conn_top and conn_top.IsConnected) else None

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

    # Corrigir curva: XY fixo pelo conector, Z dos endpoints mantidos
    loc.Curve = Line.CreateBound(
        XYZ(ref_x, ref_y, p_bot.Z),
        XYZ(ref_x, ref_y, p_top.Z)
    )

    # Reconectar inferior
    if bot_ref:
        new_conn = get_endpoint_connector(pipe, XYZ(ref_x, ref_y, p_bot.Z))
        if new_conn:
            try:
                new_conn.ConnectTo(bot_ref)
            except Exception:
                pass

    # Reconectar superior (se existia)
    if top_ref:
        new_conn = get_endpoint_connector(pipe, XYZ(ref_x, ref_y, p_top.Z))
        if new_conn:
            try:
                new_conn.ConnectTo(top_ref)
            except Exception:
                pass


def try_align_vertical(element, connected_connector):
    """Verifica se o elemento e um tubo quase vertical e alinha se for."""
    if not element.Category:
        return
    if get_id_val(element.Category.Id) != int(BuiltInCategory.OST_PipeCurves):
        return
    if not is_nearly_vertical(element):
        return
    align_vertical_pipe(element, connected_connector)


# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        with forms.WarningBar(title="PASSO 1/2: Elemento ALVO"):
            ref1 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione elemento ALVO (fixo)"
            )

        target_element = doc.GetElement(ref1)
        target_point = ref1.GlobalPoint

        with forms.WarningBar(title="PASSO 2/2: Elemento a MOVER"):
            ref2 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione elemento a MOVER"
            )

        moved_element = doc.GetElement(ref2)
        moved_point = ref2.GlobalPoint

        if target_element.Id == moved_element.Id:
            forms.alert(
                "Voce selecionou o mesmo elemento duas vezes!",
                title="Erro de Selecao",
                warn_icon=True,
                exitscript=True
            )

        cm_moved = get_connector_manager(moved_element)
        cm_target = get_connector_manager(target_element)

        moved_connector = get_connector_closest_to(cm_moved.UnusedConnectors, moved_point)
        target_connector = get_connector_closest_to(cm_target.UnusedConnectors, target_point)

        if not moved_connector or not target_connector:
            forms.alert(
                "Nao ha conectores disponiveis.",
                title="Sem Conectores",
                warn_icon=True,
                exitscript=True
            )

        is_valid, error_msg = validate_connectors_compatible(
            moved_connector,
            target_connector,
            allow_connected=False
        )

        if not is_valid:
            forms.alert(
                "Conectores incompativeis!\n\n{}".format(error_msg),
                title="Erro de Validacao",
                warn_icon=True,
                exitscript=True
            )

        with revit.Transaction("Conectar Movendo Pro"):
            success = connect_elements(
                moved_element,
                moved_connector,
                target_connector,
                auto_disconnect=True
            )

            if success:
                # Apos conectar: se tubo quase vertical, alinhar automaticamente
                # O target_connector define o XY de referencia (ponto fixo)
                try_align_vertical(moved_element, target_connector)
            else:
                forms.alert(
                    "Falha ao conectar elementos.",
                    title="Erro",
                    warn_icon=True
                )

    except OperationCanceledException:
        pass

    except AttributeError:
        forms.alert(
            "Elemento sem conectores MEP.",
            title="Erro de Validacao",
            warn_icon=True
        )

    except Exception as e:
        import traceback
        forms.alert(
            "Erro:\n\n{}".format(traceback.format_exc()),
            title="Erro",
            warn_icon=True
        )


if __name__ == "__main__":
    main()
