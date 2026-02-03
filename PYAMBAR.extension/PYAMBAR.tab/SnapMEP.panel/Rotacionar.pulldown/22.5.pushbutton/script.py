# -*- coding: utf-8 -*-
__title__ = "Rotacionar 22.5°"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0"
__doc__ = """Rotaciona conexão MEP 22.5°"""

import clr
clr.AddReference("System")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, script
from Snippets import _mep_rotation, _transaction

ANGLE_DEG = 22.5

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
    
    angle_rad = _mep_rotation.degrees_to_radians(ANGLE_DEG)
    
    with _transaction.ef_Transaction(doc, "Rotacionar 22.5°", debug=False):
        ElementTransformUtils.RotateElement(doc, element.Id, axis, angle_rad)
    
except OperationCanceledException:
    pass
except SystemExit:
    pass
except Exception as e:
    output.print_md("❌ **Erro:** {}".format(str(e)))
    import traceback
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
