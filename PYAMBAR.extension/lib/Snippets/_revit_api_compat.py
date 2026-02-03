# -*- coding: utf-8 -*-
"""
Camada de Compatibilidade da API do Revit
Centraliza todas as diferenças de versão e fornece interface unificada

Autor: Thiago Barreto Sobral Nunes
Versão: 1.0
Data: 2025-12-19
Revit Target: 2026 (com fallback para versões anteriores)

PROPÓSITO:
Este módulo resolve inconsistências da API do Revit entre versões,
fornecendo uma interface única e estável para todas as ferramentas PYAMBAR.

CASOS DE USO:
1. FilterStringRule - Assinatura mudou entre versões
2. ElementId.Value vs IntegerValue - API 2024+
3. ICollection vs List Python - Conversões .NET
4. ParameterFilterRuleFactory - Requer ParameterValueProvider
"""

import clr
clr.AddReference("System")
clr.AddReference("System.Collections")

from System.Collections.Generic import List, IList
from Autodesk.Revit.DB import *
from Autodesk.Revit.ApplicationServices import Application

# ============================================================================
# DETECÇÃO DE VERSÃO
# ============================================================================

def get_revit_version(app=None):
    """
    Obtém versão do Revit como inteiro.

    Args:
        app (Application): Aplicação Revit (opcional)

    Returns:
        int: Ano da versão (ex: 2026)

    Example:
        >>> version = get_revit_version()
        >>> if version >= 2024:
        >>>     # Usar API nova
    """
    try:
        if app is None:
            # Tentar obter da aplicação global
            from pyrevit import HOST_APP
            return int(HOST_APP.version)
        return int(app.VersionNumber)
    except:
        # Fallback: assumir versão recente
        return 2026


# ============================================================================
# ELEMENTID - Compatibilidade entre versões
# ============================================================================

def get_element_id_value(element_id, rvt_year=None):
    """
    Obtém valor inteiro de ElementId compatível com todas as versões.

    Args:
        element_id (ElementId): ID do elemento
        rvt_year (int): Ano do Revit (opcional, auto-detecta)

    Returns:
        int: Valor inteiro do ID

    Note:
        Revit 2024+: Usa .Value (long)
        Revit 2023-: Usa .IntegerValue (int)

    Example:
        >>> elem_id = element.Id
        >>> id_value = get_element_id_value(elem_id)
        >>> print("Element ID: {}".format(id_value))
    """
    if rvt_year is None:
        rvt_year = get_revit_version()

    try:
        if rvt_year >= 2024:
            # API 2024+: ElementId.Value (long)
            return int(element_id.Value) if hasattr(element_id, 'Value') else int(element_id.ToString())
        else:
            # API antiga: ElementId.IntegerValue
            return element_id.IntegerValue
    except:
        # Fallback: conversão de string
        return int(element_id.ToString())


# ============================================================================
# FILTER RULES - Compatibilidade de assinatura
# ============================================================================

def create_string_filter_rule(param_id, string_value, case_sensitive=False):
    """
    Cria FilterStringRule compatível com todas as versões.

    Args:
        param_id (ElementId): ID do parâmetro
        string_value (str): Valor para comparar
        case_sensitive (bool): Case sensitive (padrão: False)

    Returns:
        FilterStringRule: Regra de filtro

    Note:
        Usa ParameterValueProvider + FilterStringEquals
        Assinatura de 3 argumentos (compatível com 2026)

    Example:
        >>> rule = create_string_filter_rule(param.Id, "SEWER")
        >>> filter = ElementParameterFilter(rule)
    """
    provider = ParameterValueProvider(param_id)
    evaluator = FilterStringEquals() if not case_sensitive else FilterStringEquals()

    # FilterStringRule: 3 argumentos (provider, evaluator, value)
    return FilterStringRule(provider, evaluator, string_value)


def create_numeric_filter_rule(param_id, numeric_value, tolerance=None):
    """
    Cria regra de filtro para valores numéricos (Double/Integer).

    Args:
        param_id (ElementId): ID do parâmetro
        numeric_value (float/int): Valor para comparar
        tolerance (float): Tolerância para Double (opcional)

    Returns:
        FilterRule: Regra de filtro

    Example:
        >>> # Integer
        >>> rule = create_numeric_filter_rule(param.Id, 42)

        >>> # Double com tolerância
        >>> rule = create_numeric_filter_rule(param.Id, 3.14, tolerance=0.001)
    """
    provider = ParameterValueProvider(param_id)

    if tolerance is not None:
        # Double com tolerância
        return ParameterFilterRuleFactory.CreateEqualsRule(provider, numeric_value, tolerance)
    else:
        # Integer ou Double sem tolerância
        return ParameterFilterRuleFactory.CreateEqualsRule(provider, numeric_value)


def create_element_id_filter_rule(param_id, element_id_value):
    """
    Cria regra de filtro para parâmetros ElementId.

    Args:
        param_id (ElementId): ID do parâmetro
        element_id_value (ElementId): Valor ElementId para comparar

    Returns:
        FilterRule: Regra de filtro

    Example:
        >>> level_id = element.LevelId
        >>> rule = create_element_id_filter_rule(param.Id, level_id)
    """
    provider = ParameterValueProvider(param_id)
    return ParameterFilterRuleFactory.CreateEqualsRule(provider, element_id_value)


def create_filter_rule_auto(param):
    """
    Cria regra de filtro automaticamente baseada no tipo de parâmetro.

    Args:
        param (Parameter): Parâmetro do Revit

    Returns:
        FilterRule: Regra de filtro ou None se tipo não suportado

    Note:
        Detecta automaticamente: String, Double, Integer, ElementId

    Example:
        >>> for param in element.Parameters:
        >>>     rule = create_filter_rule_auto(param)
        >>>     if rule:
        >>>         # Usar regra
    """
    storage_type = param.StorageType

    try:
        if storage_type == StorageType.String:
            string_value = param.AsString()
            if string_value is None:
                return None
            return create_string_filter_rule(param.Id, string_value)

        elif storage_type == StorageType.Double:
            return create_numeric_filter_rule(param.Id, param.AsDouble(), tolerance=0.0001)

        elif storage_type == StorageType.Integer:
            return create_numeric_filter_rule(param.Id, param.AsInteger())

        elif storage_type == StorageType.ElementId:
            return create_element_id_filter_rule(param.Id, param.AsElementId())

        else:
            return None
    except:
        return None


# ============================================================================
# COLEÇÕES .NET - Conversões Python ↔ .NET
# ============================================================================

def to_net_list(python_iterable, element_type):
    """
    Converte iterável Python para List[T] do .NET.

    Args:
        python_iterable (list/tuple/set): Coleção Python
        element_type (Type): Tipo .NET (ex: ElementId, Element)

    Returns:
        List[T]: Lista .NET tipada

    Example:
        >>> python_ids = [elem1.Id, elem2.Id, elem3.Id]
        >>> net_list = to_net_list(python_ids, ElementId)
        >>> view.IsolateElementsTemporary(net_list)
    """
    return List[element_type](python_iterable)


def to_python_list(net_collection):
    """
    Converte coleção .NET para lista Python.

    Args:
        net_collection (ICollection/IList): Coleção .NET

    Returns:
        list: Lista Python

    Example:
        >>> net_ids = collector.ToElementIds()
        >>> python_ids = to_python_list(net_ids)
        >>> for id in python_ids:
        >>>     # Usar ID
    """
    return list(net_collection)


def to_ilist(python_iterable, element_type):
    """
    Converte iterável Python para IList[T] do .NET.

    Args:
        python_iterable (list/tuple/set): Coleção Python
        element_type (Type): Tipo .NET

    Returns:
        IList[T]: Interface de lista .NET

    Note:
        Alguns métodos da API exigem IList em vez de List
    """
    net_list = List[element_type](python_iterable)
    return IList[element_type](net_list)


# ============================================================================
# FILTROS COMBINADOS - Helpers avançados
# ============================================================================

def create_combined_filter(filter_rules, logic_type="AND"):
    """
    Cria filtro combinado a partir de múltiplas regras.

    Args:
        filter_rules (list): Lista de FilterRule
        logic_type (str): "AND" ou "OR" (padrão: "AND")

    Returns:
        ElementFilter: Filtro combinado

    Note:
        - 1 regra: ElementParameterFilter simples
        - >1 regra + AND: LogicalAndFilter
        - >1 regra + OR: LogicalOrFilter

    Example:
        >>> rules = [rule1, rule2, rule3]
        >>> combined = create_combined_filter(rules, logic_type="AND")
        >>> collector = FilteredElementCollector(doc).WherePasses(combined)
    """
    if len(filter_rules) == 0:
        return None

    if len(filter_rules) == 1:
        return ElementParameterFilter(filter_rules[0])

    # Múltiplas regras
    param_filters = [ElementParameterFilter(rule) for rule in filter_rules]

    if logic_type.upper() == "OR":
        return LogicalOrFilter(param_filters)
    else:
        return LogicalAndFilter(param_filters)


def create_quick_collection_filter(doc, filter_rules, logic_type="AND", include_types=False):
    """
    Cria FilteredElementCollector pronto para uso com regras.

    Args:
        doc (Document): Documento Revit
        filter_rules (list): Lista de FilterRule
        logic_type (str): "AND" ou "OR"
        include_types (bool): Incluir tipos de elementos (padrão: False)

    Returns:
        FilteredElementCollector: Coletor configurado

    Example:
        >>> rules = [rule1, rule2]
        >>> collector = create_quick_collection_filter(doc, rules)
        >>> elements = collector.ToElements()
    """
    combined_filter = create_combined_filter(filter_rules, logic_type)

    collector = FilteredElementCollector(doc).WherePasses(combined_filter)

    if not include_types:
        collector = collector.WhereElementIsNotElementType()

    return collector


# ============================================================================
# ISOLAMENTO TEMPORÁRIO - Helpers de vista
# ============================================================================

def isolate_elements_in_view(view, element_ids):
    """
    Isola elementos na vista (wrapper seguro).

    Args:
        view (View): Vista do Revit
        element_ids (list/ICollection): IDs dos elementos

    Returns:
        bool: True se sucesso

    Note:
        Converte automaticamente para List[ElementId] se necessário

    Example:
        >>> python_ids = [elem1.Id, elem2.Id]
        >>> isolate_elements_in_view(active_view, python_ids)
    """
    try:
        # Verificar se já é coleção .NET
        if isinstance(element_ids, (list, tuple, set)):
            net_list = to_net_list(element_ids, ElementId)
        else:
            net_list = element_ids

        view.IsolateElementsTemporary(net_list)
        return True
    except Exception as e:
        print("Erro ao isolar elementos: {}".format(str(e)))
        return False


def unisolate_elements_in_view(view):
    """
    Remove isolamento temporário da vista.

    Args:
        view (View): Vista do Revit

    Returns:
        bool: True se sucesso
    """
    try:
        view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate)
        return True
    except:
        return False


# ============================================================================
# UTILITÁRIOS DE PARÂMETROS
# ============================================================================

def get_parameter_value_safe(element, param_name):
    """
    Obtém valor de parâmetro de forma segura.

    Args:
        element (Element): Elemento Revit
        param_name (str): Nome do parâmetro

    Returns:
        str/None: Valor do parâmetro ou None

    Example:
        >>> value = get_parameter_value_safe(element, "Mark")
        >>> if value:
        >>>     print("Mark: {}".format(value))
    """
    try:
        param = element.LookupParameter(param_name)
        if param and param.HasValue:
            if param.StorageType == StorageType.String:
                return param.AsString()
            else:
                return param.AsValueString()
        return None
    except:
        return None


def set_parameter_value_safe(element, param_name, value):
    """
    Define valor de parâmetro de forma segura.

    Args:
        element (Element): Elemento Revit
        param_name (str): Nome do parâmetro
        value (str): Valor para definir

    Returns:
        bool: True se sucesso

    Note:
        Requer transação ativa
    """
    try:
        param = element.LookupParameter(param_name)
        if param and not param.IsReadOnly:
            param.Set(value)
            return True
        return False
    except:
        return False


# ============================================================================
# EXPORTAÇÃO
# ============================================================================

__all__ = [
    # Versão
    'get_revit_version',

    # ElementId
    'get_element_id_value',

    # Filter Rules
    'create_string_filter_rule',
    'create_numeric_filter_rule',
    'create_element_id_filter_rule',
    'create_filter_rule_auto',

    # Coleções
    'to_net_list',
    'to_python_list',
    'to_ilist',

    # Filtros Combinados
    'create_combined_filter',
    'create_quick_collection_filter',

    # Isolamento
    'isolate_elements_in_view',
    'unisolate_elements_in_view',

    # Parâmetros
    'get_parameter_value_safe',
    'set_parameter_value_safe',
]
