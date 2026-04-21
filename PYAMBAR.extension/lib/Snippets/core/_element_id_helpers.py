# -*- coding: utf-8 -*-
"""
Element ID helpers — compatibilidade Revit 2024/2026.
Delega para pyrevit.compat.get_elementid_value_func() (deteccao automatica de versao).
"""
from pyrevit.compat import get_elementid_value_func

get_element_id_value = get_elementid_value_func()
