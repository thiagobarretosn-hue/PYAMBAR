# -*- coding: utf-8 -*-
"""
Ocultar Por Parâmetro v4.3.0
Oculta elementos em vistas baseado em valores de parâmetros

Autor: Thiago Barreto Sobral Nunes
Versão: 4.3.0
Data: 2026-01-19

CHANGELOG:
v4.3.0 - Lista de parâmetros com valores (igual ao Isolar)
v4.2.0 - Fluxo igual ao Isolar (seleciona elemento de referência)
v4.1.0 - Interface limpa e fluida (sem outputs excessivos)
"""

__title__ = "Ocultar por\nParâmetro"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.3.1"

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

import os
import sys
import json
from datetime import datetime

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from pyrevit import revit, DB, forms
from System.Collections.Generic import List
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from Snippets.core._revit_version_helpers import get_element_id_value

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc

# Diretório de logs (silencioso)
LOG_DIR = os.path.expanduser("~/.pyrevit_hide_logs")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except:
        LOG_DIR = None

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def save_operation_log(operation_data):
    """Salva log da operação (silencioso)."""
    if not LOG_DIR:
        return
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, "hide_{}.json".format(timestamp))
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(operation_data, f, indent=2, ensure_ascii=False)
    except:
        pass


def get_parameter_dict_categorized(element):
    """Extrai parâmetros com valor e categorização visual."""
    parameters_dict = {}

    for param in element.Parameters:
        # Ignorar sem valor
        if not param.HasValue:
            continue

        param_name = param.Definition.Name

        # Ignorar parâmetros internos/inúteis
        if param_name.startswith("-") or param_name.startswith("_"):
            continue

        # Obter valor como string
        try:
            if param.StorageType == DB.StorageType.String:
                param_value_str = param.AsString()
            else:
                param_value_str = param.AsValueString()

            if not param_value_str:
                continue
        except:
            continue

        # Categorizar (Shared, Built-in, Custom)
        if param.IsShared:
            category = "Shared"
            emoji = "🔗"
        else:
            try:
                param_id_value = param.Id.IntegerValue if hasattr(param.Id, 'IntegerValue') else param.Id.Value
                if param_id_value < 0:
                    category = "Built-in"
                    emoji = "📦"
                else:
                    category = "Custom"
                    emoji = "⚙️"
            except:
                category = "Custom"
                emoji = "⚙️"

        # Display: emoji + nome + valor
        display_text = "{} {} : {}".format(emoji, param_name, param_value_str)
        parameters_dict[display_text] = (param, category, param_value_str)

    return parameters_dict


def group_parameters_by_category(param_dict):
    """Agrupa parâmetros por categoria para display organizado."""
    grouped = {"Built-in": [], "Shared": [], "Custom": []}

    for display_text, (_, category, _) in param_dict.items():
        grouped[category].append(display_text)

    for category in grouped:
        grouped[category].sort()

    result = []

    if grouped["Shared"]:
        result.append("═══ 🔗 SHARED ═══")
        result.extend(grouped["Shared"])
        result.append("")

    if grouped["Built-in"]:
        result.append("═══ 📦 BUILT-IN ═══")
        result.extend(grouped["Built-in"])
        result.append("")

    if grouped["Custom"]:
        result.append("═══ ⚙️ CUSTOM ═══")
        result.extend(grouped["Custom"])

    return result


def get_param_value_as_string(param):
    """Converte valor do parâmetro para string."""
    try:
        storage = param.StorageType
        if storage == DB.StorageType.String:
            return param.AsString()
        elif storage == DB.StorageType.Integer:
            return str(param.AsInteger())
        elif storage == DB.StorageType.Double:
            return str(param.AsDouble())
        elif storage == DB.StorageType.ElementId:
            elem_id = param.AsElementId()
            elem = doc.GetElement(elem_id)
            return elem.Name if elem else str(get_element_id_value(elem_id))
    except:
        pass
    return None


def get_parameter_values(elements, param_name):
    """Agrupa elementos por valor do parâmetro."""
    values_dict = {}
    for elem in elements:
        try:
            param = elem.LookupParameter(param_name)
            if param and param.HasValue:
                value = get_param_value_as_string(param)
                if value:
                    if value not in values_dict:
                        values_dict[value] = []
                    values_dict[value].append(elem)
        except:
            pass
    return values_dict


def get_all_views():
    """Obtém todas as vistas válidas do projeto."""
    collector = DB.FilteredElementCollector(doc).OfClass(DB.View)
    views = []
    for view in collector:
        try:
            if not view.IsTemplate and view.CanBePrinted:
                views.append(view)
        except:
            pass
    return sorted(views, key=lambda v: v.Name)


def hide_in_view(view, elements):
    """Oculta elementos em uma vista."""
    ids_list = List[DB.ElementId]()
    for elem in elements:
        try:
            if elem.Category and view.CanCategoryBeHidden(elem.Category.Id):
                ids_list.Add(elem.Id)
        except:
            pass

    if ids_list.Count > 0:
        try:
            view.HideElements(ids_list)
            return ids_list.Count
        except:
            pass
    return 0


# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    """Função principal - Workflow igual ao Isolar."""
    try:
        # 1. SELEÇÃO DE ELEMENTO DE REFERÊNCIA
        selected_ids = uidoc.Selection.GetElementIds()

        if not selected_ids or selected_ids.Count == 0:
            try:
                reference = uidoc.Selection.PickObject(
                    ObjectType.Element,
                    "Selecione elemento de referência"
                )
                selected_element = doc.GetElement(reference.ElementId)
            except OperationCanceledException:
                return
        else:
            selected_element = doc.GetElement(list(selected_ids)[0])

        if not selected_element:
            forms.alert("Nenhum elemento selecionado.", warn_icon=True)
            return

        element_category = selected_element.Category.Name if selected_element.Category else "N/A"

        # 2. EXTRAIR PARÂMETROS COM VALORES
        parameters_dict = get_parameter_dict_categorized(selected_element)
        if not parameters_dict:
            forms.alert("Nenhum parâmetro encontrado.", warn_icon=True)
            return

        # Lista agrupada por categoria
        grouped_list = group_parameters_by_category(parameters_dict)

        selected_display = forms.SelectFromList.show(
            grouped_list,
            title="Escolha o Parâmetro para Ocultar",
            button_name="Ocultar",
            multiselect=False
        )
        if not selected_display:
            return

        # Ignorar se selecionou header
        if selected_display.startswith("═══") or not selected_display.strip():
            forms.alert("Selecione um parâmetro válido.", warn_icon=True)
            return

        # Obter parâmetro e valor selecionado
        ref_param, _, selected_value = parameters_dict[selected_display]
        selected_param = ref_param.Definition.Name

        # 4. BUSCAR ELEMENTOS COM MESMO VALOR NO MODELO
        all_elements = list(DB.FilteredElementCollector(doc).WhereElementIsNotElementType())
        elements_to_hide = []

        for elem in all_elements:
            try:
                param = elem.LookupParameter(selected_param)
                if param and param.HasValue:
                    value = get_param_value_as_string(param)
                    if value == selected_value:
                        elements_to_hide.append(elem)
            except:
                pass

        if not elements_to_hide:
            forms.alert("Nenhum elemento encontrado.", warn_icon=True)
            return

        # 5. ESCOLHER ESCOPO
        scope_options = [
            "Vista Atual ({})".format(doc.ActiveView.Name),
            "Todas as Vistas"
        ]

        selected_scope = forms.CommandSwitchWindow.show(
            scope_options,
            message="Ocultar {} elementos\n{} = {}".format(
                len(elements_to_hide), selected_param, selected_value
            )
        )
        if not selected_scope:
            return

        scope_is_current = (selected_scope == scope_options[0])

        # 6. EXECUTAR
        t = DB.Transaction(doc, "Ocultar por Parâmetro")
        t.Start()

        try:
            if scope_is_current:
                view = doc.ActiveView
                hidden = hide_in_view(view, elements_to_hide)
                t.Commit()

                save_operation_log({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "parameter": selected_param,
                    "value": selected_value,
                    "hidden": hidden,
                    "view": view.Name
                })

                forms.alert(
                    "{} elementos ocultados\n"
                    "Categoria: {}\n"
                    "{} = {}".format(hidden, element_category, selected_param, selected_value),
                    title="Concluído"
                )
            else:
                views = get_all_views()
                total_hidden = 0
                views_modified = 0

                for view in views:
                    hidden = hide_in_view(view, elements_to_hide)
                    if hidden > 0:
                        total_hidden += hidden
                        views_modified += 1

                t.Commit()

                save_operation_log({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "parameter": selected_param,
                    "value": selected_value,
                    "total_hidden": total_hidden,
                    "views_modified": views_modified
                })

                forms.alert(
                    "{} elementos ocultados\n"
                    "{} vistas modificadas\n"
                    "{} = {}".format(total_hidden, views_modified, selected_param, selected_value),
                    title="Concluído"
                )

        except Exception as e:
            t.RollBack()
            forms.alert("Erro: {}".format(str(e)), warn_icon=True)

    except OperationCanceledException:
        pass

    except Exception as e:
        import traceback
        forms.alert("Erro: {}\n\n{}".format(str(e), traceback.format_exc()), warn_icon=True)


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == '__main__':
    main()
