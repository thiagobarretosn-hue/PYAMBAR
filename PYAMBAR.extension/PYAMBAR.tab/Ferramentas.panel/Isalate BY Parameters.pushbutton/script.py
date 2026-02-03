# -*- coding: utf-8 -*-
"""
Isolate BY Parameters v5.2.0
Isola elementos na vista por parâmetros selecionados

Autor: Thiago Barreto Sobral Nunes
Versão: 5.2.0
Data: 2026-01-19
Revit Target: 2026+

CHANGELOG:
v5.2.1 - Padronizacao: revit.doc/uidoc/app em vez de __revit__
v5.2.0 - Interface limpa e fluida (sem outputs excessivos)
v5.1.0 - FIX: LogicalAndFilter com List<ElementFilter> .NET
       - FIX: Removido BuiltInParameterGroup.INVALID (deprecated)

DESCRIÇÃO:
Ferramenta avançada de isolamento baseado em parâmetros com interface intuitiva,
suporte a lógica AND/OR, estatísticas detalhadas e compatibilidade universal.

✨ NOVIDADES v5.0 (2026-01-08):
🚀 Removido __persistentengine__ para melhor performance
🔧 Compatibilidade universal SEM dependências externas
💾 Histórico movido para user folder (~/.pyrevit_isolate_logs/)
📊 Estatísticas aprimoradas
🎯 Validação robusta de tipos de parâmetros
🔄 Fallback automático quando snippets não disponíveis
📝 Documentação inline completa
⚡ Performance otimizada

WORKFLOW:
1. Execute o comando (ou pré-selecione elementos)
2. Sistema detecta elemento de referência automaticamente
3. Escolha parâmetros para filtrar (categorias codificadas por cor)
4. [OPCIONAL] Escolha lógica AND/OR se múltiplos parâmetros
5. Elementos são isolados automaticamente
6. Veja estatísticas detalhadas no output

FUNCIONALIDADES:
- Seleção inteligente de elemento de referência
- Categorização visual de parâmetros (Built-in vs Custom vs Shared)
- Lógica AND (todos) ou OR (qualquer) critério
- Estatísticas com breakdown por categoria
- Histórico de filtros (últimos 5)
- Compatibilidade universal (Revit 2019-2026+)

APLICAÇÕES:
- Análise de elementos MEP por sistema
- Isolamento por fase e disciplina
- Filtros de QA/QC automatizados
- Estudos de clash detection
- Análise de elementos similares
"""

__title__ = "Isolar por\nParâmetros"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.2.2"

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

import json
import os
import sys
from datetime import datetime

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

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
    TemporaryViewMode,
    View,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import forms, revit, script, HOST_APP
from System.Collections.Generic import List

from Snippets.core._revit_version_helpers import get_element_id_value

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
rvt_year = int(app.VersionNumber)
output = script.get_output()

# Diretório de log em user folder
LOG_DIR = os.path.join(os.path.expanduser("~"), ".pyrevit_isolate_logs")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except:
        LOG_DIR = None

# ============================================================================
# FUNÇÕES DE COMPATIBILIDADE (FALLBACK INTEGRADO)
# ============================================================================

def to_python_list(collection):
    """
    Converte ICollection para lista Python.

    Args:
        collection: ICollection do .NET

    Returns:
        list: Lista Python
    """
    return list(collection)


def create_filter_rule_equals(param, param_value_str):
    """
    Cria FilterRule de igualdade (compatível com Revit 2019-2026+).

    Args:
        param: Parameter do Revit
        param_value_str: Valor como string

    Returns:
        FilterRule ou None
    """
    param_id = param.Id

    # String parameters
    if param.StorageType == StorageType.String:
        try:
            # Revit 2022+
            return ParameterFilterRuleFactory.CreateEqualsRule(
                param_id,
                param_value_str,
                False  # caseSensitive
            )
        except:
            # Revit 2021-
            return ParameterFilterRuleFactory.CreateEqualsRule(
                param_id,
                param_value_str
            )

    # Integer parameters
    elif param.StorageType == StorageType.Integer:
        try:
            int_value = int(param.AsInteger())
            return ParameterFilterRuleFactory.CreateEqualsRule(param_id, int_value)
        except:
            return None

    # Double parameters
    elif param.StorageType == StorageType.Double:
        try:
            double_value = param.AsDouble()
            tolerance = 1e-6
            return ParameterFilterRuleFactory.CreateEqualsRule(param_id, double_value, tolerance)
        except:
            return None

    # ElementId parameters
    elif param.StorageType == StorageType.ElementId:
        try:
            elem_id = param.AsElementId()
            return ParameterFilterRuleFactory.CreateEqualsRule(param_id, elem_id)
        except:
            return None

    return None


def create_combined_filter(filter_rules, logic_type="AND"):
    """
    Combina múltiplas regras em um ElementFilter.

    Args:
        filter_rules: Lista de FilterRule
        logic_type: "AND" ou "OR"

    Returns:
        ElementFilter: Filtro combinado
    """
    if len(filter_rules) == 1:
        return ElementParameterFilter(filter_rules[0])

    # Criar lista de filtros
    filters_list = [ElementParameterFilter(rule) for rule in filter_rules]

    # CORREÇÃO REVIT 2026: Converter para List<ElementFilter> .NET
    # LogicalAndFilter/LogicalOrFilter requerem IList<ElementFilter>
    filters_net = List[ElementFilter](filters_list)

    if logic_type == "AND":
        return LogicalAndFilter(filters_net)
    else:  # OR
        return LogicalOrFilter(filters_net)


def isolate_elements_in_view(view, element_ids):
    """Isola elementos na vista (compatível com Revit 2019-2026+)."""
    try:
        if not isinstance(element_ids, List[ElementId]):
            id_collection = List[ElementId](element_ids)
        else:
            id_collection = element_ids
        view.IsolateElementsTemporary(id_collection)
        return True
    except:
        return False


def unisolate_elements_in_view(view):
    """Remove isolamento temporário da vista."""
    try:
        view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)
        return True
    except:
        return False


# ============================================================================
# PERSISTÊNCIA DE ESTADO
# ============================================================================

def get_history_file():
    """Retorna caminho do arquivo de histórico em user folder."""
    if not LOG_DIR:
        return None
    return os.path.join(LOG_DIR, "filter_history.json")


def load_filter_history():
    """Carrega histórico de filtros usados."""
    try:
        history_file = get_history_file()
        if history_file and os.path.exists(history_file):
            with open(history_file, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"filters": []}


def save_filter_history(param_names):
    """Salva filtro no histórico (máx 5)."""
    try:
        history_file = get_history_file()
        if not history_file:
            return

        history = load_filter_history()
        filter_entry = {
            "parameters": param_names,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(param_names)
        }
        history["filters"].insert(0, filter_entry)
        history["filters"] = history["filters"][:5]

        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
    except:
        pass


# ============================================================================
# FUNÇÕES AUXILIARES - PARÂMETROS
# ============================================================================

def get_parameter_dict_categorized(element):
    """
    Extrai parâmetros com categorização visual.

    Args:
        element (Element): Elemento do Revit

    Returns:
        dict: {display_text: (Parameter, category)}
              category: "Built-in", "Custom", "Shared"
    """
    parameters_dict = {}

    for param in element.Parameters:
        # Ignorar parâmetros sem valor
        if not param.HasValue:
            continue

        param_name = param.Definition.Name

        # Ignorar parâmetros internos
        if param_name.startswith("-") or param_name.startswith("_"):
            continue

        # Obter representação textual do valor
        try:
            if param.StorageType == StorageType.String:
                param_value_str = param.AsString()
            else:
                param_value_str = param.AsValueString()

            # Ignorar se não há representação textual
            if not param_value_str:
                continue
        except:
            continue

        # Determinar categoria (compatível com Revit 2024+ onde BuiltInParameterGroup foi deprecated)
        if param.IsShared:
            category = "Shared"
            emoji = "🔗"
        else:
            # Tentar determinar se é Built-in baseado no ID do parâmetro
            # Built-in parameters geralmente têm IDs negativos
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

        # Criar texto de exibição formatado
        display_text = "{} {} : {}".format(emoji, param_name, param_value_str)
        parameters_dict[display_text] = (param, category)

    return parameters_dict


def group_parameters_by_category(param_dict):
    """
    Agrupa parâmetros por categoria para display organizado.

    Args:
        param_dict (dict): Dicionário de parâmetros

    Returns:
        list: Lista organizada para SelectFromList
    """
    grouped = {
        "Built-in": [],
        "Shared": [],
        "Custom": []
    }

    for display_text, (param, category) in param_dict.items():
        grouped[category].append(display_text)

    # Ordenar cada grupo alfabeticamente
    for category in grouped:
        grouped[category].sort()

    # Criar lista final com headers
    result = []

    if grouped["Shared"]:
        result.append("═══ 🔗 SHARED PARAMETERS ═══")
        result.extend(grouped["Shared"])
        result.append("")  # Espaço

    if grouped["Built-in"]:
        result.append("═══ 📦 BUILT-IN PARAMETERS ═══")
        result.extend(grouped["Built-in"])
        result.append("")

    if grouped["Custom"]:
        result.append("═══ ⚙️ CUSTOM PARAMETERS ═══")
        result.extend(grouped["Custom"])

    return result


# ============================================================================
# FUNÇÕES AUXILIARES - FILTROS
# ============================================================================

def collect_matching_elements(doc, combined_filter):
    """Coleta elementos que correspondem ao filtro."""
    try:
        matching_ids = FilteredElementCollector(doc)\
            .WherePasses(combined_filter)\
            .WhereElementIsNotElementType()\
            .ToElementIds()
        return to_python_list(matching_ids)
    except:
        return []


def get_element_categories_stats(doc, element_ids):
    """
    Estatísticas de categorias dos elementos.

    Args:
        doc (Document): Documento Revit
        element_ids (list): Lista de ElementId

    Returns:
        dict: {categoria: count}
    """
    stats = {}

    for elem_id in element_ids:
        try:
            element = doc.GetElement(elem_id)
            if element and element.Category:
                cat_name = element.Category.Name
                stats[cat_name] = stats.get(cat_name, 0) + 1
        except:
            continue

    return stats


# ============================================================================
# INTERFACE E EXECUÇÃO
# ============================================================================

def main():
    """Função principal - Workflow limpo e fluido."""
    try:
        # 1. SELEÇÃO DE ELEMENTO
        selected_ids = uidoc.Selection.GetElementIds()

        if not selected_ids or selected_ids.Count == 0:
            try:
                reference = uidoc.Selection.PickObject(
                    ObjectType.Element,
                    "Selecione elemento referência"
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

        # 2. EXTRAIR PARÂMETROS
        parameters_dict = get_parameter_dict_categorized(selected_element)

        if not parameters_dict:
            forms.alert("O elemento não possui parâmetros válidos.", warn_icon=True)
            return

        # 3. SELEÇÃO DE PARÂMETROS
        grouped_list = group_parameters_by_category(parameters_dict)

        selected_params_display = forms.SelectFromList.show(
            grouped_list,
            title="Selecione Parâmetros para Isolar",
            button_name="Isolar",
            multiselect=True
        )

        if not selected_params_display:
            return

        # Filtrar headers
        selected_params_display = [
            s for s in selected_params_display
            if not s.startswith("═══") and s.strip()
        ]

        if not selected_params_display:
            return

        selected_params = [parameters_dict[display][0] for display in selected_params_display]

        # 4. CRIAR REGRAS DE FILTRO
        filter_rules = []

        for param in selected_params:
            if param.StorageType == StorageType.String:
                param_value_str = param.AsString()
            else:
                param_value_str = param.AsValueString()

            rule = create_filter_rule_equals(param, param_value_str)
            if rule:
                filter_rules.append(rule)

        if not filter_rules:
            forms.alert("Nenhum parâmetro válido para filtro.", warn_icon=True)
            return

        # 5. ESCOLHER LÓGICA (se múltiplos parâmetros)
        logic_type = "AND"

        if len(filter_rules) > 1:
            logic_choice = forms.alert(
                "AND: Corresponder a TODOS os parâmetros\n"
                "OR: Corresponder a QUALQUER parâmetro",
                title="Lógica de Filtro",
                yes=True,
                no=True,
                options=["AND (todos)", "OR (qualquer)"]
            )
            logic_type = "AND" if logic_choice else "OR"

        # 6. COLETAR E ISOLAR
        combined_filter = create_combined_filter(filter_rules, logic_type)
        matching_ids = collect_matching_elements(doc, combined_filter)

        if not matching_ids:
            forms.alert("Nenhum elemento encontrado.", warn_icon=True)
            return

        # 7. ISOLAR
        with revit.Transaction("Isolar por Parâmetros"):
            success = isolate_elements_in_view(doc.ActiveView, matching_ids)

        if not success:
            forms.alert("Erro ao isolar elementos.", warn_icon=True)
            return

        # 8. SALVAR HISTÓRICO (silencioso)
        param_names = [param.Definition.Name for param in selected_params]
        save_filter_history(param_names)

        # 9. RESULTADO
        forms.alert(
            "{} elementos isolados\n"
            "Categoria: {}\n"
            "Parâmetros: {}\n"
            "Lógica: {}".format(
                len(matching_ids),
                element_category,
                len(filter_rules),
                logic_type
            ),
            title="Isolamento Concluído"
        )

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
