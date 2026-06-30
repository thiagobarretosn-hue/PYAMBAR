import os, sys
# -*- coding: utf-8 -*-
__title__ = "Rotacionar 90°"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.0"
__doc__ = """Rotaciona conexões MEP 90°
Suporta múltiplos elementos selecionados."""

import clr
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, script, forms

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from Snippets import _mep_rotation, _transaction

ANGLE_DEG = 90.0

doc = revit.doc
uidoc = revit.uidoc

try:
    sel_ids = uidoc.Selection.GetElementIds()
    if sel_ids.Count > 0:
        elements = [doc.GetElement(eid) for eid in sel_ids]
    else:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, "Selecione as conexões MEP")
        if not refs:
            raise SystemExit
        elements = [doc.GetElement(r.ElementId) for r in refs]

    to_rotate = []
    for elem in elements:
        if not isinstance(elem, FamilyInstance):
            continue
        axis = _mep_rotation.get_rotation_axis(elem)
        if axis:
            to_rotate.append((elem, axis))

    if not to_rotate:
        forms.alert("Nenhuma conexão MEP válida na seleção.", warn_icon=True)
        raise SystemExit

    angle_rad = _mep_rotation.degrees_to_radians(ANGLE_DEG)

    with _transaction.ef_Transaction(doc, "Rotacionar {}x {}°".format(len(to_rotate), ANGLE_DEG), debug=False):
        for elem, axis in to_rotate:
            ElementTransformUtils.RotateElement(doc, elem.Id, axis, angle_rad)

except OperationCanceledException:
    pass
except SystemExit:
    pass
except Exception as e:
    forms.alert("Erro: {}".format(str(e)))
