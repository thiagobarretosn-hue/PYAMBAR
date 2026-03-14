# -*- coding: utf-8 -*-
__title__ = "Rotacionar Conexão"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.0"
__doc__ = """Rotaciona conexões MEP com seleção de ângulo
Suporta múltiplos elementos selecionados."""

import clr
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script
from Snippets import _mep_rotation, _transaction

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

try:
    # Usar selecao atual ou pedir para selecionar
    sel_ids = uidoc.Selection.GetElementIds()
    if sel_ids.Count > 0:
        elements = [doc.GetElement(eid) for eid in sel_ids]
    else:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, "Selecione as conexões MEP")
        if not refs:
            raise SystemExit
        elements = [doc.GetElement(r.ElementId) for r in refs]

    # Filtrar apenas FamilyInstance com eixo valido
    to_rotate = []
    for elem in elements:
        if not isinstance(elem, FamilyInstance):
            continue
        axis = _mep_rotation.get_rotation_axis(elem)
        if axis:
            to_rotate.append((elem, axis))

    if not to_rotate:
        output.print_md("**Nenhuma conexão MEP válida na seleção.**")
        raise SystemExit

    # Escolher angulo
    angle_options = {
        "Girar 22.5°": 22.5,
        "Girar 90°": 90.0,
        "Girar 180°": 180.0,
        "Girar 270°": 270.0
    }

    selected_key = forms.CommandSwitchWindow.show(
        angle_options.keys(),
        message="Ângulo para {} elemento(s)".format(len(to_rotate))
    )

    if not selected_key:
        raise SystemExit

    angle_deg = angle_options[selected_key]
    angle_rad = _mep_rotation.degrees_to_radians(angle_deg)

    with _transaction.ef_Transaction(doc, "Rotacionar {}x {}°".format(len(to_rotate), angle_deg), debug=False):
        for elem, axis in to_rotate:
            ElementTransformUtils.RotateElement(doc, elem.Id, axis, angle_rad)

except OperationCanceledException:
    pass
except SystemExit:
    pass
except Exception as e:
    output.print_md("**Erro:** {}".format(str(e)))
    import traceback
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
