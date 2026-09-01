# -*- coding: utf-8 -*-
"""
_mep_common.py — o que as fases de conexao MEP compartilham.

Estas funcoes existiam em copia em cada modulo (motor, desvio, derivacao), e
cada copia foi um bug separado: o tipo de sistema invalido quebrou o desvio, a
derivacao e quase o motor em tres rodadas diferentes, porque a correcao numa
copia nao alcancava as outras. Uma definicao so, um lugar para corrigir.

O que NAO entra aqui: logica que divergiu de proposito entre os modulos.
``_set_free_end``, por exemplo, tem tres versoes com tolerancias diferentes e
so a do motor preserva a conexao da ponta ancorada — unifica-las exigiria
decidir qual comportamento vale para todos, e isso muda resultado. Fica para
uma etapa propria, com a bancada validando antes e depois.
"""

import math


def advance_for(offset, angle_deg):
    """Avanco no eixo para vencer ``offset`` com um joelho de ``angle_deg``.

    Em 90 graus o joelho sobe reto e nao consome nada no eixo.
    """
    if angle_deg >= 89.99:
        return 0.0
    return offset / math.tan(math.radians(angle_deg))


def conn_at(elem, ponto, tol=0.02):
    """Conector de extremidade de ``elem`` no ``ponto``, ou None.

    Serve tubo e fitting: o primeiro expoe ConnectorManager direto, o segundo
    atraves de MEPModel.
    """
    try:
        cm = elem.ConnectorManager
    except AttributeError:
        try:
            cm = elem.MEPModel.ConnectorManager
        except Exception:
            return None
    except Exception:
        return None
    try:
        for conn in cm.Connectors:
            if conn.Origin.DistanceTo(ponto) < tol:
                return conn
    except Exception:
        return None
    return None


def system_type_id(pipe, doc=None):
    """Tipo de sistema utilizavel para criar tubo a partir de ``pipe``.

    A armadilha que custou tres rodadas de teste: um tubo sem sistema NAO vem
    com MEPSystem nulo. O Revit lhe da um sistema "Nao definido", cujo
    GetTypeId() e InvalidElementId — e esse -1 faz Pipe.Create recusar com
    "The systemTypeId is not valid piping system type", derrubando a fase
    inteira. Cada fonte so vale se der um id de verdade.

    Devolve None quando nem o documento tem um tipo de sistema.
    """
    from Autodesk.Revit.DB import (BuiltInParameter, ElementId,
                                   FilteredElementCollector)
    from Autodesk.Revit.DB.Plumbing import PipingSystemType

    if doc is None:
        from pyrevit import revit
        doc = revit.doc

    try:
        sistema = pipe.MEPSystem
        if sistema is not None:
            tipo = sistema.GetTypeId()
            if tipo is not None and tipo != ElementId.InvalidElementId:
                return tipo
    except Exception:
        pass

    try:
        prm = pipe.get_Parameter(BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM)
        if prm is not None:
            eid = prm.AsElementId()
            if eid is not None and eid != ElementId.InvalidElementId:
                return eid
    except Exception:
        pass

    try:
        for st in FilteredElementCollector(doc).OfClass(PipingSystemType):
            return st.Id
    except Exception:
        pass
    return None
