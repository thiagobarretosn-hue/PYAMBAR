# -*- coding: utf-8 -*-
"""
_revit_version_helpers.py
Funções auxiliares para compatibilidade entre versões do Revit.

USAGE:
    from Snippets.core._revit_version_helpers import get_id_value, get_revit_year
    # ou alias para compatibilidade:
    from Snippets.core._revit_version_helpers import get_element_id_value

    element_id = element.Id
    id_int = get_id_value(element_id)

    year = get_revit_year()
    if year >= 2024:
        # Código específico para 2024+
        pass

DEPENDENCIES:
    - Autodesk.Revit.DB
    - Autodesk.Revit.ApplicationServices

AUTHOR: Thiago Barreto
VERSION: 1.0
"""

from Autodesk.Revit.DB import *
from Autodesk.Revit.ApplicationServices import *


def get_revit_year():
    """
    Retorna o ano da versão do Revit em execução.

    Returns:
        int: Ano da versão (ex: 2024, 2026)

    Example:
        >>> year = get_revit_year()
        >>> print(year)
        2026
    """
    from pyrevit import HOST_APP
    return int(HOST_APP.version)


def get_id_value(element_or_id):
    """
    Obtém valor inteiro do ElementId com compatibilidade entre versões.

    Revit 2024+ usa ElementId.Value
    Revit 2023- usa ElementId.IntegerValue (deprecated)

    Args:
        element_or_id: Elemento do Revit ou ElementId

    Returns:
        int: Valor inteiro do ElementId, ou -1 se falhar

    Example:
        >>> wall = UnwrapElement(some_wall)
        >>> id_value = get_id_value(wall)       # aceita Element
        >>> id_value = get_id_value(wall.Id)    # aceita ElementId
        >>> print(id_value)
        123456
    """
    try:
        # Se for um elemento, obter o Id primeiro
        elem_id = element_or_id.Id if hasattr(element_or_id, 'Id') else element_or_id

        # Tentar .Value primeiro (Revit 2024+)
        if hasattr(elem_id, 'Value'):
            return elem_id.Value
        # Fallback para .IntegerValue (Revit 2023-)
        elif hasattr(elem_id, 'IntegerValue'):
            return elem_id.IntegerValue
        else:
            # Último recurso: conversão via string
            return int(elem_id.ToString())
    except:
        return -1


def obter_tipo_parametro(tipo_str):
    """
    Converte string para ParameterType (Revit 2023-) ou ForgeTypeId (Revit 2024+).

    Args:
        tipo_str (str): Nome do tipo ('TEXT', 'NUMBER', 'LENGTH', 'AREA', 'VOLUME', etc.)

    Returns:
        ParameterType ou ForgeTypeId: Tipo apropriado para a versão do Revit

    Example:
        >>> param_type = obter_tipo_parametro('TEXT')
        >>> # Revit 2023-: retorna ParameterType.Text
        >>> # Revit 2024+: retorna SpecTypeId.String.Text
    """
    rvt_year = get_revit_year()

    # Mapeamento de tipos comuns
    TIPOS_MAP_PRE2024 = {
        'TEXT': ParameterType.Text,
        'NUMBER': ParameterType.Number,
        'INTEGER': ParameterType.Integer,
        'LENGTH': ParameterType.Length,
        'AREA': ParameterType.Area,
        'VOLUME': ParameterType.Volume,
        'ANGLE': ParameterType.Angle,
        'YESNO': ParameterType.YesNo,
        'URL': ParameterType.URL,
    }

    if rvt_year >= 2024:
        # Revit 2024+: usar ForgeTypeId
        from Autodesk.Revit.DB import SpecTypeId

        TIPOS_MAP_2024 = {
            'TEXT': SpecTypeId.String.Text,
            'NUMBER': SpecTypeId.Number,
            'INTEGER': SpecTypeId.Int.Integer,
            'LENGTH': SpecTypeId.Length,
            'AREA': SpecTypeId.Area,
            'VOLUME': SpecTypeId.Volume,
            'ANGLE': SpecTypeId.Angle,
            'YESNO': SpecTypeId.Boolean.YesNo,
            'URL': SpecTypeId.String.Url,
        }

        return TIPOS_MAP_2024.get(tipo_str.upper(), SpecTypeId.String.Text)
    else:
        # Revit 2023-: usar ParameterType (deprecated)
        return TIPOS_MAP_PRE2024.get(tipo_str.upper(), ParameterType.Text)


def obter_parameter_group(group_str):
    """
    Converte string para BuiltInParameterGroup (Revit 2023-) ou ForgeTypeId (Revit 2024+).

    Args:
        group_str (str): Nome do grupo ('GEOMETRY', 'IDENTITY_DATA', 'CONSTRAINTS', etc.)

    Returns:
        BuiltInParameterGroup ou ForgeTypeId: Grupo apropriado para a versão

    Example:
        >>> group = obter_parameter_group('GEOMETRY')
        >>> # Revit 2023-: retorna BuiltInParameterGroup.PG_GEOMETRY
        >>> # Revit 2024+: retorna GroupTypeId.Geometry
    """
    rvt_year = get_revit_year()

    # Mapeamento de grupos comuns
    GROUPS_MAP_PRE2024 = {
        'GEOMETRY': BuiltInParameterGroup.PG_GEOMETRY,
        'IDENTITY_DATA': BuiltInParameterGroup.PG_IDENTITY_DATA,
        'CONSTRAINTS': BuiltInParameterGroup.PG_CONSTRAINTS,
        'DATA': BuiltInParameterGroup.PG_DATA,
        'TEXT': BuiltInParameterGroup.PG_TEXT,
        'GENERAL': BuiltInParameterGroup.PG_GENERAL,
    }

    if rvt_year >= 2024:
        # Revit 2024+: usar GroupTypeId
        from Autodesk.Revit.DB import GroupTypeId

        GROUPS_MAP_2024 = {
            'GEOMETRY': GroupTypeId.Geometry,
            'IDENTITY_DATA': GroupTypeId.IdentityData,
            'CONSTRAINTS': GroupTypeId.Constraints,
            'DATA': GroupTypeId.Data,
            'TEXT': GroupTypeId.Text,
            'GENERAL': GroupTypeId.General,
        }

        return GROUPS_MAP_2024.get(group_str.upper(), GroupTypeId.General)
    else:
        # Revit 2023-: usar BuiltInParameterGroup (deprecated)
        return GROUPS_MAP_PRE2024.get(group_str.upper(), BuiltInParameterGroup.PG_GENERAL)


# ALIAS para compatibilidade com código legado
get_element_id_value = get_id_value


# TESTES UNITÁRIOS (executar apenas quando módulo é executado diretamente)
if __name__ == '__main__':
    print("=== TESTANDO _revit_version_helpers.py ===\n")

    # Teste 1: get_revit_year
    year = get_revit_year()
    print("1. get_revit_year(): {}".format(year))
    assert year >= 2020, "Ano inválido"

    # Teste 2: get_id_value
    test_id = ElementId(123456)
    id_val = get_id_value(test_id)
    print("2. get_id_value(123456): {}".format(id_val))
    assert id_val == 123456, "ID value incorreto"

    # Teste 3: obter_tipo_parametro
    tipo_text = obter_tipo_parametro('TEXT')
    print("3. obter_tipo_parametro('TEXT'): {}".format(tipo_text))

    # Teste 4: obter_parameter_group
    group_geom = obter_parameter_group('GEOMETRY')
    print("4. obter_parameter_group('GEOMETRY'): {}".format(group_geom))

    print("\n✅ TODOS OS TESTES PASSARAM!")
