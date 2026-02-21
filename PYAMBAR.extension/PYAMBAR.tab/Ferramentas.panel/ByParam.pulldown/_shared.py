# -*- coding: utf-8 -*-
"""
_shared.py - Logica central do pulldown ByParam v1.0
Importar de cada pushbutton filho:

    import os, sys
    PULLDOWN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
    if PULLDOWN_DIR not in sys.path:
        sys.path.insert(0, PULLDOWN_DIR)
    from _shared import run_action
    if __name__ == '__main__':
        run_action("isolate")  # ou "hide" | "select" | "3d"
"""

import traceback

import clr
clr.AddReference("System")

from Autodesk.Revit.DB import (
    ElementFilter,
    ElementId,
    ElementParameterFilter,
    FilteredElementCollector,
    LogicalAndFilter,
    LogicalOrFilter,
    ParameterFilterRuleFactory,
    StorageType,
    View,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List

from pyrevit import forms, revit

doc   = revit.doc
uidoc = revit.uidoc

# ============================================================================
# HELPERS - REFERENCIA E PARAMETROS
# ============================================================================

def _get_reference_element():
    """Retorna elemento de referencia: pre-selecionado ou pick."""
    selected_ids = uidoc.Selection.GetElementIds()
    if selected_ids and selected_ids.Count > 0:
        return doc.GetElement(list(selected_ids)[0])
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.Element,
            "Selecione o elemento de referencia"
        )
        return doc.GetElement(ref.ElementId)
    except OperationCanceledException:
        return None


def _get_param_dict(element):
    """
    Retorna {display_text: (param_obj, val_str)} para params com valor.
    Inclui parametros de instancia e de tipo.
    """
    result = {}

    def _collect_from(obj):
        if not obj:
            return
        for param in obj.Parameters:
            if not param.HasValue:
                continue
            name = param.Definition.Name
            if name.startswith("-") or name.startswith("_"):
                continue
            try:
                if param.StorageType == StorageType.String:
                    val_str = param.AsString()
                else:
                    val_str = param.AsValueString()
                if not val_str or not val_str.strip():
                    continue
            except:
                continue

            # Emoji por tipo
            if param.IsShared:
                emoji = "🔗"
            else:
                try:
                    pid = param.Id.Value if hasattr(param.Id, 'Value') else param.Id.IntegerValue
                    emoji = "📦" if pid < 0 else "⚙️"
                except:
                    emoji = "⚙️"

            display = "{} {} : {}".format(emoji, name, val_str)
            if display not in result:
                result[display] = (param, val_str)

    # Instancia
    _collect_from(element)

    # Tipo (nao duplicar chaves)
    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            elem_type = doc.GetElement(type_id)
            _collect_from(elem_type)
    except:
        pass

    return result


def _grouped_list(param_dict):
    """Organiza params em grupos Shared / Built-in / Custom para SelectFromList."""
    shared, builtin, custom = [], [], []

    for display, (param, _) in param_dict.items():
        if param.IsShared:
            shared.append(display)
        else:
            try:
                pid = param.Id.Value if hasattr(param.Id, 'Value') else param.Id.IntegerValue
                (builtin if pid < 0 else custom).append(display)
            except:
                custom.append(display)

    shared.sort()
    builtin.sort()
    custom.sort()

    result = []
    if shared:
        result.append("═══ 🔗 SHARED ═══")
        result.extend(shared)
        result.append("")
    if builtin:
        result.append("═══ 📦 BUILT-IN ═══")
        result.extend(builtin)
        result.append("")
    if custom:
        result.append("═══ ⚙️ CUSTOM ═══")
        result.extend(custom)
    return result


# ============================================================================
# HELPERS - FILTROS E COLETA
# ============================================================================

def _create_filter_rule(param):
    """
    Cria FilterRule baseada no valor REAL do parametro (nao em string formatada).
    Suporta String, Integer, Double e ElementId.
    """
    try:
        pid = param.Id
        st  = param.StorageType

        if st == StorageType.String:
            val = param.AsString() or ""
            try:
                return ParameterFilterRuleFactory.CreateEqualsRule(pid, val)
            except TypeError:
                return ParameterFilterRuleFactory.CreateEqualsRule(pid, val, False)

        elif st == StorageType.Integer:
            return ParameterFilterRuleFactory.CreateEqualsRule(pid, param.AsInteger())

        elif st == StorageType.Double:
            return ParameterFilterRuleFactory.CreateEqualsRule(pid, param.AsDouble(), 1e-6)

        elif st == StorageType.ElementId:
            return ParameterFilterRuleFactory.CreateEqualsRule(pid, param.AsElementId())

    except Exception:
        pass
    return None


def _collect_matching(selected_params, logic):
    """
    Coleta TODOS os elementos do projeto que batem com os parametros selecionados.
    Independente de categoria - usa FilteredElementCollector(doc) sem categoria.
    Retorna lista de ElementId.
    """
    rules = []
    for param in selected_params:
        rule = _create_filter_rule(param)
        if rule:
            rules.append(rule)

    if not rules:
        return []

    # Montar filtro combinado
    if len(rules) == 1:
        combined = ElementParameterFilter(rules[0])
    else:
        elem_filters = List[ElementFilter]([ElementParameterFilter(r) for r in rules])
        if logic == "AND":
            combined = LogicalAndFilter(elem_filters)
        else:
            combined = LogicalOrFilter(elem_filters)

    try:
        ids = list(
            FilteredElementCollector(doc)
            .WherePasses(combined)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
        return ids
    except Exception as e:
        print("AVISO: Filtro falhou ({}). Nenhum elemento retornado.".format(str(e)))
        return []


def _find_3d_view():
    """Retorna vista 3D: ativa > {3D} > qualquer."""
    try:
        active = doc.ActiveView
        vtype = str(active.ViewType)
        if "ThreeD" in vtype and not active.IsTemplate:
            return active
    except:
        pass

    any_3d = None
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            vtype = str(v.ViewType)
            if "ThreeD" in vtype and not v.IsTemplate:
                if v.Name == "{3D}":
                    return v
                if any_3d is None:
                    any_3d = v
        except:
            pass
    return any_3d


# ============================================================================
# ACOES
# ============================================================================

def _do_isolate(ids):
    """Isola temporariamente na vista ativa."""
    id_list = List[ElementId](ids)
    with revit.Transaction("ByParam: Isolar"):
        doc.ActiveView.IsolateElementsTemporary(id_list)
    uidoc.RefreshActiveView()
    return len(ids)


def _do_select(ids):
    """Seleciona elementos na vista (sem transaction)."""
    uidoc.Selection.SetElementIds(List[ElementId](ids))
    return len(ids)


def _do_hide(ids, scope):
    """
    Oculta elementos.
    scope: "active" (vista ativa) ou "all" (todas as vistas).
    Retorna (count_hidden, views_modified).
    """
    elements = []
    for eid in ids:
        try:
            elem = doc.GetElement(eid)
            if elem:
                elements.append(elem)
        except:
            pass

    def _hide_in_view(view, elems):
        hide_ids = List[ElementId]()
        for elem in elems:
            try:
                if elem.Category and view.CanCategoryBeHidden(elem.Category.Id):
                    hide_ids.Add(elem.Id)
            except:
                pass
        if hide_ids.Count > 0:
            try:
                view.HideElements(hide_ids)
            except:
                pass
        return hide_ids.Count

    with revit.Transaction("ByParam: Ocultar"):
        if scope == "active":
            count = _hide_in_view(doc.ActiveView, elements)
            return count, 1
        else:
            total = 0
            views_modified = 0
            for v in FilteredElementCollector(doc).OfClass(View):
                try:
                    if not v.IsTemplate and v.CanBePrinted:
                        c = _hide_in_view(v, elements)
                        if c > 0:
                            total += c
                            views_modified += 1
                except:
                    pass
            return total, views_modified


def _do_3d(ids):
    """Abre vista 3D e isola elementos."""
    view3d = _find_3d_view()
    if not view3d:
        forms.alert("Nenhuma vista 3D encontrada no projeto.", exitscript=False)
        return 0

    id_list = List[ElementId](ids)
    with revit.Transaction("ByParam: Vista 3D"):
        view3d.IsolateElementsTemporary(id_list)
    uidoc.ActiveView = view3d
    uidoc.RefreshActiveView()
    return len(ids)


# ============================================================================
# ENTRY POINT CENTRAL
# ============================================================================

_ACTION_LABELS = {
    "isolate": "Isolar Temporariamente",
    "hide":    "Ocultar",
    "select":  "Selecionar",
    "3d":      "Vista 3D",
}


def run_action(action_type):
    """
    Executa o fluxo completo para a acao especificada.
    action_type: "isolate" | "hide" | "select" | "3d"
    """
    try:
        label = _ACTION_LABELS.get(action_type, action_type)

        # 1. Elemento de referencia
        ref = _get_reference_element()
        if not ref:
            return

        # 2. Parametros com valor (instancia + tipo)
        param_dict = _get_param_dict(ref)
        if not param_dict:
            forms.alert(
                "Elemento sem parametros com valor.\n"
                "Selecione outro elemento de referencia.",
                warn_icon=True
            )
            return

        # 3. Picker de parametros
        grouped = _grouped_list(param_dict)
        selected_display = forms.SelectFromList.show(
            grouped,
            title="{} por Parametros".format(label),
            button_name=label,
            multiselect=True
        )
        if not selected_display:
            return

        # Remover headers
        selected_display = [
            s for s in selected_display
            if not s.startswith("═══") and s.strip()
        ]
        if not selected_display:
            return

        selected_params = [param_dict[d][0] for d in selected_display]

        # 4. Logica AND / OR (apenas se multiplos)
        logic = "AND"
        if len(selected_params) > 1:
            opts = [
                "AND - Todos os criterios (elemento deve ter TODOS)",
                "OR  - Qualquer criterio (elemento deve ter UM)",
            ]
            choice = forms.CommandSwitchWindow.show(
                opts,
                message="Logica para {} parametros selecionados:".format(len(selected_params))
            )
            if not choice:
                return
            logic = "AND" if "AND" in choice else "OR"

        # 5. Coletar elementos do projeto inteiro
        matching_ids = _collect_matching(selected_params, logic)
        if not matching_ids:
            forms.alert(
                "Nenhum elemento encontrado no projeto com esses valores de parametro.\n\n"
                "Verifique se o parametro e filtravel (Shared ou Built-in).",
                warn_icon=True
            )
            return

        # 6. Executar acao
        if action_type == "isolate":
            count = _do_isolate(matching_ids)
            forms.alert(
                "{} elementos isolados na vista ativa.".format(count),
                title=label
            )

        elif action_type == "select":
            count = _do_select(matching_ids)
            forms.alert(
                "{} elementos selecionados.".format(count),
                title=label
            )

        elif action_type == "hide":
            scope_opts = [
                "Vista Ativa ({})".format(doc.ActiveView.Name),
                "Todas as Vistas",
            ]
            scope_choice = forms.CommandSwitchWindow.show(
                scope_opts,
                message="Ocultar {} elementos - escopo:".format(len(matching_ids))
            )
            if not scope_choice:
                return
            scope = "active" if scope_choice == scope_opts[0] else "all"
            count, views = _do_hide(matching_ids, scope)
            if scope == "active":
                forms.alert(
                    "{} elementos ocultados na vista ativa.".format(count),
                    title=label
                )
            else:
                forms.alert(
                    "{} elementos ocultados em {} vistas.".format(count, views),
                    title=label
                )

        elif action_type == "3d":
            count = _do_3d(matching_ids)
            if count:
                forms.alert(
                    "{} elementos na vista 3D.".format(count),
                    title=label
                )

    except OperationCanceledException:
        pass
    except Exception as e:
        forms.alert(
            "Erro: {}\n\n{}".format(str(e), traceback.format_exc()),
            warn_icon=True
        )
