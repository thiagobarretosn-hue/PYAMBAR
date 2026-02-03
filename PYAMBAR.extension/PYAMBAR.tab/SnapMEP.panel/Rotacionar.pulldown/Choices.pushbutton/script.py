# -*- coding: utf-8 -*-
__title__ = "Rotacionar Conexão"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0"
__doc__ = """Rotaciona conexão MEP com seleção de ângulo"""

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
    ref = uidoc.Selection.PickObject(ObjectType.Element, "Selecione a conexão MEP")
    element = doc.GetElement(ref.ElementId)
    
    if not isinstance(element, FamilyInstance):
        output.print_md("❌ **Erro:** Elemento não é conexão MEP")
        raise SystemExit
    
    axis = _mep_rotation.get_rotation_axis(element)
    if not axis:
        output.print_md("❌ **Erro:** Elemento sem conectores válidos")
        raise SystemExit
    
    angle_options = {
        "Girar 22.5°": 22.5,
        "Girar 90°": 90.0,
        "Girar 180°": 180.0,
        "Girar 270°": 270.0
    }
    
    selected_key = forms.CommandSwitchWindow.show(
        angle_options.keys(),
        message="Ângulo para: {}".format(element.Name)
    )
    
    if not selected_key:
        raise SystemExit
    
    angle_deg = angle_options[selected_key]
    angle_rad = _mep_rotation.degrees_to_radians(angle_deg)
    
    with _transaction.ef_Transaction(doc, "Rotacionar {}°".format(angle_deg), debug=False):
        ElementTransformUtils.RotateElement(doc, element.Id, axis, angle_rad)
    
except OperationCanceledException:
    pass
except SystemExit:
    pass
except Exception as e:
    output.print_md("❌ **Erro:** {}".format(str(e)))
    import traceback
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
