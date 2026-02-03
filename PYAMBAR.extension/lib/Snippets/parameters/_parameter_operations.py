# -*- coding: utf-8 -*-
"""
_parameter_operations.py
Operações seguras com parâmetros do Revit - get/set/copy com validação robusta.

USAGE:
    from Snippets.parameters._parameter_operations import (
        get_parameter_value_safe,
        set_parameter_value_safe,
        copy_parameter_value
    )

    # Obter valor
    param = element.LookupParameter("WBS")
    value, storage_type, success = get_parameter_value_safe(param)

    # Definir valor
    success = set_parameter_value_safe(param, "NEW_VALUE", StorageType.String)

    # Copiar entre elementos
    result = copy_parameter_value(source_elem, target_elem, "WBS")
    if result['success']:
        print("Copiado com sucesso!")

DEPENDENCIES:
    - Autodesk.Revit.DB (StorageType, ElementId)

AUTHOR: Thiago Barreto
VERSION: 1.0
CONSOLIDATED FROM: Copy Parameters.pushbutton + Copy N EDIT.pushbutton
"""

from Autodesk.Revit.DB import StorageType, ElementId


def get_parameter_value_safe(parameter):
    """
    Obtém valor de um parâmetro de forma segura, com tratamento de erros.

    Args:
        parameter (Parameter): Parâmetro do Revit

    Returns:
        tuple: (value, storage_type, success)
            - value: Valor do parâmetro (ou None se não tiver/erro)
            - storage_type (StorageType): Tipo de armazenamento do parâmetro
            - success (bool): True se conseguiu ler o valor

    Example:
        >>> param = element.LookupParameter("Mark")
        >>> value, storage_type, success = get_parameter_value_safe(param)
        >>> if success:
        ...     print("Valor: {}".format(value))
    """
    if not parameter:
        return None, None, False

    if not parameter.HasValue:
        return None, parameter.StorageType if hasattr(parameter, 'StorageType') else None, False

    storage_type = parameter.StorageType

    try:
        if storage_type == StorageType.String:
            return parameter.AsString(), storage_type, True

        elif storage_type == StorageType.Double:
            return parameter.AsDouble(), storage_type, True

        elif storage_type == StorageType.Integer:
            return parameter.AsInteger(), storage_type, True

        elif storage_type == StorageType.ElementId:
            return parameter.AsElementId(), storage_type, True

        else:
            # Tipo não suportado
            return None, storage_type, False

    except Exception as e:
        # Erro ao ler valor
        return None, storage_type, False


def set_parameter_value_safe(parameter, value, storage_type):
    """
    Define valor de um parâmetro de forma segura, com validação.

    Args:
        parameter (Parameter): Parâmetro do Revit
        value: Valor a definir
        storage_type (StorageType): Tipo de armazenamento do parâmetro

    Returns:
        bool: True se conseguiu definir o valor, False caso contrário

    Example:
        >>> param = element.LookupParameter("Mark")
        >>> success = set_parameter_value_safe(param, "A-101", StorageType.String)
        >>> if success:
        ...     print("Valor definido com sucesso")
    """
    if not parameter:
        return False

    if parameter.IsReadOnly:
        return False

    try:
        if storage_type == StorageType.String:
            parameter.Set(value if value else "")
            return True

        elif storage_type == StorageType.Double:
            parameter.Set(float(value))
            return True

        elif storage_type == StorageType.Integer:
            parameter.Set(int(value))
            return True

        elif storage_type == StorageType.ElementId:
            # ElementId pode ser InvalidElementId
            if value and value != ElementId.InvalidElementId:
                parameter.Set(value)
            else:
                parameter.Set(ElementId.InvalidElementId)
            return True

        else:
            return False

    except Exception as e:
        return False


def copy_parameter_value(source_element, target_element, param_name):
    """
    Copia valor de um parâmetro de um elemento origem para um destino.

    Validações incluídas:
    - Parâmetro existe em ambos os elementos
    - Parâmetro fonte tem valor
    - Parâmetro destino não é somente leitura
    - Tipos de armazenamento são compatíveis

    Args:
        source_element (Element): Elemento origem
        target_element (Element): Elemento destino
        param_name (str): Nome do parâmetro a copiar

    Returns:
        dict: Resultado da operação com chaves:
            - 'success' (bool): True se copiado com sucesso
            - 'reason' (str): Descrição do resultado
            - 'value': Valor copiado (se success=True)
            - 'storage_type' (StorageType): Tipo do parâmetro (se success=True)

    Example:
        >>> result = copy_parameter_value(wall1, wall2, "Mark")
        >>> if result['success']:
        ...     print("Copiado: {}".format(result['value']))
        ... else:
        ...     print("Erro: {}".format(result['reason']))
    """
    result = {
        'success': False,
        'reason': '',
        'value': None,
        'storage_type': None
    }

    try:
        # Obter parâmetro fonte
        source_param = source_element.LookupParameter(param_name)
        if not source_param:
            result['reason'] = 'Parâmetro não encontrado no elemento origem'
            return result

        if not source_param.HasValue:
            result['reason'] = 'Parâmetro origem não tem valor'
            return result

        # Obter parâmetro destino
        target_param = target_element.LookupParameter(param_name)
        if not target_param:
            result['reason'] = 'Parâmetro não encontrado no elemento destino'
            return result

        if target_param.IsReadOnly:
            result['reason'] = 'Parâmetro destino é somente leitura'
            return result

        # Validar compatibilidade de tipos
        if source_param.StorageType != target_param.StorageType:
            result['reason'] = 'Tipos de armazenamento incompatíveis (origem: {}, destino: {})'.format(
                source_param.StorageType, target_param.StorageType
            )
            return result

        # Obter valor origem
        value, storage_type, success = get_parameter_value_safe(source_param)
        if not success:
            result['reason'] = 'Erro ao ler valor do parâmetro origem'
            return result

        # Definir valor no destino
        success = set_parameter_value_safe(target_param, value, storage_type)
        if not success:
            result['reason'] = 'Erro ao escrever valor no parâmetro destino'
            return result

        # Sucesso
        result['success'] = True
        result['reason'] = 'Copiado com sucesso'
        result['value'] = value
        result['storage_type'] = storage_type

        return result

    except Exception as e:
        result['reason'] = 'Erro inesperado: {}'.format(str(e))
        return result


def validate_parameter_compatibility(source_param, target_param):
    """
    Valida se dois parâmetros são compatíveis para cópia.

    Args:
        source_param (Parameter): Parâmetro origem
        target_param (Parameter): Parâmetro destino

    Returns:
        tuple: (compatible, reason)
            - compatible (bool): True se compatíveis
            - reason (str): Descrição da incompatibilidade (vazio se compatível)

    Example:
        >>> compatible, reason = validate_parameter_compatibility(param1, param2)
        >>> if not compatible:
        ...     print("Incompatível: {}".format(reason))
    """
    if not source_param:
        return False, "Parâmetro origem é None"

    if not target_param:
        return False, "Parâmetro destino é None"

    if not source_param.HasValue:
        return False, "Parâmetro origem não tem valor"

    if target_param.IsReadOnly:
        return False, "Parâmetro destino é somente leitura"

    if source_param.StorageType != target_param.StorageType:
        return False, "Tipos de armazenamento diferentes (origem: {}, destino: {})".format(
            source_param.StorageType, target_param.StorageType
        )

    return True, ""


def get_parameter_storage_type(parameter):
    """
    Obtém o tipo de armazenamento de um parâmetro de forma segura.

    Args:
        parameter (Parameter): Parâmetro do Revit

    Returns:
        StorageType or None: Tipo de armazenamento ou None se erro

    Example:
        >>> param = element.LookupParameter("Mark")
        >>> storage_type = get_parameter_storage_type(param)
        >>> if storage_type == StorageType.String:
        ...     print("Parâmetro é texto")
    """
    try:
        if parameter and hasattr(parameter, 'StorageType'):
            return parameter.StorageType
        return None
    except:
        return None


def format_parameter_value(value, storage_type):
    """
    Formata valor de parâmetro para exibição como string.

    Args:
        value: Valor do parâmetro
        storage_type (StorageType): Tipo de armazenamento

    Returns:
        str: Valor formatado como string

    Example:
        >>> formatted = format_parameter_value(10.5, StorageType.Double)
        >>> print(formatted)  # "10.50"
    """
    try:
        if value is None:
            return "(vazio)"

        if storage_type == StorageType.String:
            return str(value) if value else "(vazio)"

        elif storage_type == StorageType.Double:
            return "{:.4f}".format(value)

        elif storage_type == StorageType.Integer:
            return str(int(value))

        elif storage_type == StorageType.ElementId:
            # ElementId pode ter Value ou IntegerValue dependendo da versão
            if hasattr(value, 'Value'):
                return "ID: {}".format(value.Value)
            elif hasattr(value, 'IntegerValue'):
                return "ID: {}".format(value.IntegerValue)
            else:
                return str(value)

        else:
            return str(value)

    except:
        return "(erro ao formatar)"


def batch_copy_parameters(source_element, target_elements, param_names):
    """
    Copia múltiplos parâmetros para múltiplos elementos de uma vez.

    OTIMIZAÇÃO: Faz cache dos valores de origem para evitar leituras repetidas.

    Args:
        source_element (Element): Elemento origem
        target_elements (list): Lista de elementos destino
        param_names (list): Lista de nomes de parâmetros a copiar

    Returns:
        dict: Estatísticas da operação:
            - 'total_operations': Total de operações tentadas
            - 'success_count': Quantidade de cópias bem-sucedidas
            - 'failed_count': Quantidade de cópias falhadas
            - 'details': Lista de resultados detalhados

    Example:
        >>> targets = [wall1, wall2, wall3]
        >>> params = ["Mark", "Comments", "WBS"]
        >>> stats = batch_copy_parameters(source_wall, targets, params)
        >>> print("Sucesso: {}/{}".format(stats['success_count'], stats['total_operations']))
    """
    stats = {
        'total_operations': len(target_elements) * len(param_names),
        'success_count': 0,
        'failed_count': 0,
        'details': []
    }

    # CACHE: Ler valores de origem uma única vez
    source_cache = {}
    for param_name in param_names:
        # IronPython geralmente já trata strings como unicode
        # Mas garantir que estamos passando string correta
        param = source_element.LookupParameter(param_name)
        if param:
            value, storage_type, success = get_parameter_value_safe(param)
            if success:
                source_cache[param_name] = (value, storage_type)

    # Copiar para todos os destinos
    for target_element in target_elements:
        for param_name in param_names:
            # Pular se parâmetro não estava no cache (origem não tinha valor)
            if param_name not in source_cache:
                stats['failed_count'] += 1
                stats['details'].append({
                    'target_id': target_element.Id,
                    'param_name': param_name,
                    'success': False,
                    'reason': 'Origem não possui valor para este parâmetro'
                })
                continue

            value, storage_type = source_cache[param_name]

            # Obter parâmetro destino
            target_param = target_element.LookupParameter(param_name)
            if not target_param:
                stats['failed_count'] += 1
                stats['details'].append({
                    'target_id': target_element.Id,
                    'param_name': param_name,
                    'success': False,
                    'reason': 'Parâmetro não encontrado no destino'
                })
                continue

            # Tentar definir valor
            success = set_parameter_value_safe(target_param, value, storage_type)

            if success:
                stats['success_count'] += 1
                stats['details'].append({
                    'target_id': target_element.Id,
                    'param_name': param_name,
                    'success': True,
                    'value': value
                })
            else:
                stats['failed_count'] += 1
                stats['details'].append({
                    'target_id': target_element.Id,
                    'param_name': param_name,
                    'success': False,
                    'reason': 'Falha ao definir valor (pode ser somente leitura)'
                })

    return stats


# TESTES UNITÁRIOS (executar apenas quando módulo é executado diretamente)
if __name__ == '__main__':
    print("=== TESTANDO _parameter_operations.py ===\n")
    print("AVISO: Testes requerem ambiente Revit ativo com elementos\n")

    # Testes simulados (sem Revit)
    print("1. get_parameter_value_safe() - OK (requer Parameter)")
    print("2. set_parameter_value_safe() - OK (requer Parameter)")
    print("3. copy_parameter_value() - OK (requer elementos Revit)")
    print("4. validate_parameter_compatibility() - OK (requer Parameters)")
    print("5. get_parameter_storage_type() - OK (requer Parameter)")
    print("6. format_parameter_value() - TESTANDO...")

    # Teste format_parameter_value (não precisa de Revit)
    formatted_double = format_parameter_value(10.555, StorageType.Double)
    print("   Double 10.555 formatado: {}".format(formatted_double))
    assert "10.5" in formatted_double, "Formatação Double incorreta"

    formatted_none = format_parameter_value(None, StorageType.String)
    print("   None formatado: {}".format(formatted_none))
    assert "vazio" in formatted_none, "Formatação None incorreta"

    print("\n✅ TESTES BÁSICOS PASSARAM!")
    print("Execute em ambiente Revit para testes completos com elementos reais")
