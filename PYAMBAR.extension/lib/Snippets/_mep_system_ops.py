# -*- coding: utf-8 -*-
"""Operacoes de PipingSystem que falam com a Revit API.

Complementa Snippets._mep_system_split, que e a logica de grafo pura. Aqui
mora o que precisa do Document: montar o grafo a partir dos ConnectorManager,
achar e refazer ligacoes, aplicar System Type.

REGRAS DO REVIT que este modulo encapsula (comprovadas por probe, 26/08/2026 —
ver memoria revit-piping-system-split-rules):

- SetSystemType vale para o PipingSystem INTEIRO, nunca para um elemento so.
- O estado de rede so materializa no COMMIT: dentro da transacao que acabou de
  desconectar, IsMultipleNetwork continua False; logo apos DivideSystem,
  MEPSystem devolve NULO. Quem le sem commitar antes escreve no lugar errado.
- DivideSystem DELETA o system de origem e cria N novos.
- Referencia de PipingSystem fica stale depois de um commit: re-obter por Id.
"""

import clr
clr.AddReference("System")

from Autodesk.Revit.DB import (
    BuiltInParameter, Element, ElementId, FamilyInstance
)
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystem


def id_value(elem_id):
    """ElementId -> int, cobrindo Revit 2024+ (.Value) e anteriores."""
    return elem_id.Value if hasattr(elem_id, 'Value') else elem_id.IntegerValue


def elem_name(element):
    """Element.Name lanca AttributeError em varios tipos no IronPython."""
    try:
        return Element.Name.GetValue(element)
    except Exception:
        return "?"


def conn_manager(element):
    """ConnectorManager de um tubo (direto) ou fitting (via MEPModel)."""
    try:
        cm = element.ConnectorManager
        if cm is not None:
            return cm
    except Exception:
        pass
    try:
        mm = element.MEPModel
        return mm.ConnectorManager if mm else None
    except Exception:
        return None


def physical_connectors(element):
    """Connectors de ligacao fisica (End/Curve), ignorando os logicos."""
    cm = conn_manager(element)
    if cm is None:
        return []
    out = []
    for con in cm.Connectors:
        try:
            if str(con.ConnectorType) in ("End", "Curve"):
                out.append(con)
        except Exception:
            pass
    return out


def element_system(element):
    """PipingSystem de um tubo ou fitting, ou None.

    Devolve None legitimamente logo apos um DivideSystem nao commitado — nesse
    estado o Revit ainda nao recalculou a rede.
    """
    try:
        sysm = element.MEPSystem
        if sysm is not None:
            return sysm
    except Exception:
        pass
    for con in physical_connectors(element):
        try:
            if con.MEPSystem is not None:
                return con.MEPSystem
        except Exception:
            pass
    return None


def build_graph(doc, systems):
    """(adjacency, fittings, system_of) dos elementos dos systems informados.

    Cobre o system inteiro, nao so os elementos de interesse — e assim que se
    descobre o que sera arrastado junto e se o resto vai se fragmentar.
    """
    adjacency = {}
    fittings = set()
    system_of = {}

    for sysm in systems:
        sys_id = id_value(sysm.Id)
        for element in sysm.PipingNetwork:
            eid = id_value(element.Id)
            system_of[eid] = sys_id
            adjacency.setdefault(eid, set())
            if isinstance(element, FamilyInstance):
                fittings.add(eid)

    for eid in list(adjacency.keys()):
        element = doc.GetElement(ElementId(eid))
        if element is None:
            continue
        for con in physical_connectors(element):
            try:
                if not con.IsConnected:
                    continue
                for ref in con.AllRefs:
                    owner = ref.Owner
                    if owner is None:
                        continue
                    oid = id_value(owner.Id)
                    if oid == eid or oid not in adjacency:
                        continue
                    adjacency[eid].add(oid)
                    adjacency[oid].add(eid)
            except Exception:
                pass
    return adjacency, fittings, system_of


def find_link(doc, id_a, id_b):
    """(connector_a, connector_b, origem) que ligam os dois elementos."""
    elem_a = doc.GetElement(ElementId(id_a))
    if elem_a is None:
        return None
    for con in physical_connectors(elem_a):
        try:
            if not con.IsConnected:
                continue
            for other in con.AllRefs:
                owner = other.Owner
                if owner is not None and id_value(owner.Id) == id_b:
                    return (con, other, con.Origin)
        except Exception:
            pass
    return None


def connector_at(element, point):
    """Connector do elemento mais proximo de um ponto.

    Como religar acontece depois de o Revit ter mexido nos elementos, o
    connector e reencontrado por posicao, nao por indice.
    """
    melhor = None
    menor = None
    for con in physical_connectors(element):
        try:
            dist = con.Origin.DistanceTo(point)
        except Exception:
            continue
        if menor is None or dist < menor:
            menor = dist
            melhor = con
    return melhor


def set_system_type(element, type_id):
    """Aplica o System Type ao system do elemento. True so se aplicou mesmo.

    Tubo tem metodo proprio; fitting vai pelo parametro. Em acessorio
    (PipeAccessory) o parametro e read-only — ignorar esse False deixa a ilha
    inteira com o type antigo.
    """
    if isinstance(element, Pipe):
        element.SetSystemType(type_id)
        return True
    prm = element.get_Parameter(BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM)
    if prm and not prm.IsReadOnly:
        prm.Set(type_id)
        return True
    return False


def apply_type_to_group(elements, type_id):
    """Aplica o type usando o primeiro elemento que aceita — tubos primeiro.

    Basta um aceitar: SetSystemType vale para o system todo. Devolve o
    elemento que funcionou, ou None se nenhum aceitou.
    """
    candidatos = ([e for e in elements if isinstance(e, Pipe)] +
                  [e for e in elements if not isinstance(e, Pipe)])
    for element in candidatos:
        try:
            if set_system_type(element, type_id):
                return element
        except Exception:
            pass
    return None


def systems_of(doc, element_ids):
    """{system_id: [element_ids]} lido AGORA, nunca reaproveitado de antes."""
    grupos = {}
    for eid in sorted(element_ids):
        element = doc.GetElement(ElementId(eid))
        if element is None:
            continue
        sysm = element_system(element)
        if sysm is None:
            continue
        grupos.setdefault(id_value(sysm.Id), []).append(eid)
    return grupos


def existing_system_names(doc):
    """Nomes de PipingSystem ja em uso — o Revit exige nome unico."""
    return set(elem_name(s) for s in FilteredElementCollector(doc)
               .OfClass(PipingSystem).WhereElementIsNotElementType()
               .ToElements())


def rename_system(doc, system_id, nome):
    """(ok, mensagem_de_erro). Tolera nome ja correto, system sumido, duplicata."""
    sysm = doc.GetElement(ElementId(system_id))
    if sysm is None:
        return False, "system do nome '{}' nao existe mais".format(nome)
    if elem_name(sysm) == nome:
        return True, None
    try:
        sysm.Name = nome
        return True, None
    except Exception as ex:
        return False, "nao consegui nomear '{}' (ficou '{}'): {}".format(
            nome, elem_name(sysm), ex)
