# -*- coding: utf-8 -*-
"""
_view3d_helpers.py
Helpers para vistas 3D: encontrar vista, section box por elementos.

USAGE:
    from Snippets.views._view3d_helpers import find_3d_view, set_section_box

    view3d = find_3d_view(doc, uidoc)
    set_section_box(doc, view3d, element_ids, padding=2.0)

DEPENDENCIES:
    - Autodesk.Revit.DB (View3D, BoundingBoxXYZ, XYZ, FilteredElementCollector)

AUTHOR: Thiago Barreto
VERSION: 1.0
"""

from Autodesk.Revit.DB import (
    FilteredElementCollector, View3D, BoundingBoxXYZ, XYZ
)


def find_3d_view(doc, uidoc=None):
    """Retorna vista 3D: ativa > {3D} > qualquer.

    Args:
        doc: Revit Document
        uidoc: UIDocument (opcional, para checar vista ativa)

    Returns:
        View3D ou None
    """
    if uidoc:
        try:
            active = uidoc.ActiveView
            if isinstance(active, View3D) and not active.IsTemplate:
                return active
        except:
            pass

    any_3d = None
    for v in FilteredElementCollector(doc).OfClass(View3D):
        try:
            if v.IsTemplate:
                continue
            if v.Name == "{3D}":
                return v
            if any_3d is None:
                any_3d = v
        except:
            pass
    return any_3d


def compute_bounding_box(doc, element_ids, padding=2.0):
    """Calcula BoundingBoxXYZ unificado de uma lista de ElementIds.

    Args:
        doc: Revit Document
        element_ids: lista de ElementId
        padding: margem em pes ao redor do bounding box (default 2.0 ~60cm)

    Returns:
        BoundingBoxXYZ ou None se nenhum elemento tem geometria
    """
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False

    for eid in element_ids:
        elem = doc.GetElement(eid)
        if not elem:
            continue
        bb = elem.get_BoundingBox(None)
        if not bb:
            continue
        found = True
        if bb.Min.X < min_x: min_x = bb.Min.X
        if bb.Min.Y < min_y: min_y = bb.Min.Y
        if bb.Min.Z < min_z: min_z = bb.Min.Z
        if bb.Max.X > max_x: max_x = bb.Max.X
        if bb.Max.Y > max_y: max_y = bb.Max.Y
        if bb.Max.Z > max_z: max_z = bb.Max.Z

    if not found:
        return None

    bbox = BoundingBoxXYZ()
    bbox.Min = XYZ(min_x - padding, min_y - padding, min_z - padding)
    bbox.Max = XYZ(max_x + padding, max_y + padding, max_z + padding)
    return bbox


def set_section_box(view3d, bbox):
    """Aplica section box numa View3D.

    Args:
        view3d: View3D do Revit
        bbox: BoundingBoxXYZ calculado

    Nota: deve ser chamado dentro de uma Transaction.
    """
    view3d.SetSectionBox(bbox)
    view3d.IsSectionBoxActive = True
