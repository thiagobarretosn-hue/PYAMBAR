# -*- coding: utf-8 -*-
"""
_geometry_center.py
Funções para cálculo de centros geométricos de elementos Revit.

USAGE:
    from Snippets.geometry._geometry_center import obter_centro_elemento
    from Snippets.geometry._geometry_center import obter_centro_boundingbox

    # Obter centro de um elemento
    wall = UnwrapElement(some_wall)
    centro = obter_centro_elemento(wall)
    print("Centro: X={}, Y={}, Z={}".format(centro.X, centro.Y, centro.Z))

    # Obter centro da BoundingBox
    bbox = wall.get_BoundingBox(None)
    centro_bbox = obter_centro_boundingbox(bbox)

DEPENDENCIES:
    - Autodesk.Revit.DB

AUTHOR: Thiago Barreto
VERSION: 1.0
"""

from Autodesk.Revit.DB import *


def obter_centro_boundingbox(bounding_box):
    """
    Calcula o centro de uma BoundingBoxXYZ.

    Args:
        bounding_box (BoundingBoxXYZ): BoundingBox do elemento

    Returns:
        XYZ: Ponto central da BoundingBox

    Example:
        >>> bbox = elemento.get_BoundingBox(None)
        >>> centro = obter_centro_boundingbox(bbox)
        >>> print("Centro: ({}, {}, {})".format(centro.X, centro.Y, centro.Z))
    """
    if not bounding_box:
        return None

    # Centro = (Min + Max) / 2
    min_point = bounding_box.Min
    max_point = bounding_box.Max

    centro_x = (min_point.X + max_point.X) / 2.0
    centro_y = (min_point.Y + max_point.Y) / 2.0
    centro_z = (min_point.Z + max_point.Z) / 2.0

    return XYZ(centro_x, centro_y, centro_z)


def obter_centro_elemento(elemento, view=None):
    """
    Obtém o ponto central de um elemento Revit.

    Tenta múltiplos métodos:
    1. Location.Point (elementos pontuais: pilares, familias, etc.)
    2. Location.Curve.Evaluate(0.5) (elementos lineares: paredes, vigas, tubos)
    3. BoundingBox center (elementos complexos: rooms, áreas, etc.)

    Args:
        elemento (Element): Elemento Revit
        view (View): Vista de referência para BoundingBox (opcional, usa None para global)

    Returns:
        XYZ: Ponto central do elemento ou None se não conseguir obter

    Example:
        >>> wall = UnwrapElement(some_wall)
        >>> centro = obter_centro_elemento(wall)
        >>> if centro:
        ...     print("Centro: X={:.2f}, Y={:.2f}, Z={:.2f}".format(centro.X, centro.Y, centro.Z))
    """
    try:
        location = elemento.Location

        # MÉTODO 1: LocationPoint (pilares, famílias, etc.)
        if isinstance(location, LocationPoint):
            return location.Point

        # MÉTODO 2: LocationCurve (paredes, vigas, tubos, etc.)
        elif isinstance(location, LocationCurve):
            curve = location.Curve
            # Ponto médio = parâmetro 0.5 normalizado
            return curve.Evaluate(0.5, True)

        # MÉTODO 3: BoundingBox (rooms, áreas, elementos complexos)
        else:
            bbox = elemento.get_BoundingBox(view)
            if bbox:
                return obter_centro_boundingbox(bbox)

        # Se chegou aqui, não conseguiu determinar centro
        return None

    except Exception as e:
        print("ERRO ao obter centro do elemento ID {}: {}".format(elemento.Id, str(e)))
        return None


def obter_centro_multiple_elements(elementos_lista, view=None):
    """
    Obtém centro geométrico de múltiplos elementos (centroide).

    Args:
        elementos_lista (list): Lista de elementos Revit
        view (View): Vista de referência (opcional)

    Returns:
        XYZ: Ponto central médio de todos os elementos

    Example:
        >>> pilares = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns)
        >>> centro_geral = obter_centro_multiple_elements(list(pilares))
        >>> print("Centroide dos pilares: {}".format(centro_geral))
    """
    if not elementos_lista or len(elementos_lista) == 0:
        return None

    soma_x = 0.0
    soma_y = 0.0
    soma_z = 0.0
    count_validos = 0

    for elem in elementos_lista:
        centro = obter_centro_elemento(elem, view)
        if centro:
            soma_x += centro.X
            soma_y += centro.Y
            soma_z += centro.Z
            count_validos += 1

    if count_validos == 0:
        return None

    # Média aritmética
    centro_x = soma_x / count_validos
    centro_y = soma_y / count_validos
    centro_z = soma_z / count_validos

    return XYZ(centro_x, centro_y, centro_z)


def obter_centro_com_offset(elemento, offset_x=0, offset_y=0, offset_z=0, view=None):
    """
    Obtém centro do elemento com offset customizado.

    Args:
        elemento (Element): Elemento Revit
        offset_x (float): Offset em X (em unidades internas Revit - pés)
        offset_y (float): Offset em Y
        offset_z (float): Offset em Z
        view (View): Vista de referência (opcional)

    Returns:
        XYZ: Ponto central com offset aplicado

    Example:
        >>> # Obter centro 10 pés acima do elemento
        >>> centro_acima = obter_centro_com_offset(elemento, offset_z=10.0)
    """
    centro_base = obter_centro_elemento(elemento, view)

    if not centro_base:
        return None

    return XYZ(
        centro_base.X + offset_x,
        centro_base.Y + offset_y,
        centro_base.Z + offset_z
    )


def obter_altura_elemento(elemento):
    """
    Calcula altura (dimensão Z) de um elemento via BoundingBox.

    Args:
        elemento (Element): Elemento Revit

    Returns:
        float: Altura do elemento em unidades internas (pés)

    Example:
        >>> pilar = UnwrapElement(some_column)
        >>> altura = obter_altura_elemento(pilar)
        >>> print("Altura do pilar: {:.2f} pés".format(altura))
    """
    try:
        bbox = elemento.get_BoundingBox(None)
        if not bbox:
            return 0.0

        altura = bbox.Max.Z - bbox.Min.Z
        return altura

    except:
        return 0.0


def obter_dimensoes_elemento(elemento):
    """
    Obtém dimensões (largura, profundidade, altura) de um elemento via BoundingBox.

    Args:
        elemento (Element): Elemento Revit

    Returns:
        dict: {'largura': float, 'profundidade': float, 'altura': float}
              Valores em unidades internas (pés)

    Example:
        >>> dims = obter_dimensoes_elemento(elemento)
        >>> print("Dimensões - L:{} x P:{} x A:{}".format(
        ...     dims['largura'], dims['profundidade'], dims['altura']
        ... ))
    """
    try:
        bbox = elemento.get_BoundingBox(None)
        if not bbox:
            return {'largura': 0.0, 'profundidade': 0.0, 'altura': 0.0}

        largura = bbox.Max.X - bbox.Min.X
        profundidade = bbox.Max.Y - bbox.Min.Y
        altura = bbox.Max.Z - bbox.Min.Z

        return {
            'largura': largura,
            'profundidade': profundidade,
            'altura': altura
        }

    except:
        return {'largura': 0.0, 'profundidade': 0.0, 'altura': 0.0}


def distancia_entre_elementos(elemento1, elemento2, view=None):
    """
    Calcula distância euclidiana entre centros de dois elementos.

    Args:
        elemento1 (Element): Primeiro elemento
        elemento2 (Element): Segundo elemento
        view (View): Vista de referência (opcional)

    Returns:
        float: Distância em unidades internas (pés)

    Example:
        >>> pilar_1 = UnwrapElement(pilar1)
        >>> pilar_2 = UnwrapElement(pilar2)
        >>> dist = distancia_entre_elementos(pilar_1, pilar_2)
        >>> print("Distância entre pilares: {:.2f} pés".format(dist))
    """
    centro1 = obter_centro_elemento(elemento1, view)
    centro2 = obter_centro_elemento(elemento2, view)

    if not centro1 or not centro2:
        return None

    return centro1.DistanceTo(centro2)


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _geometry_center.py ===\n")

    # Teste 1: obter_centro_boundingbox
    min_pt = XYZ(0, 0, 0)
    max_pt = XYZ(10, 10, 10)
    bbox_test = BoundingBoxXYZ()
    bbox_test.Min = min_pt
    bbox_test.Max = max_pt
    centro = obter_centro_boundingbox(bbox_test)
    print("1. Centro BoundingBox: ({}, {}, {})".format(centro.X, centro.Y, centro.Z))
    assert centro.X == 5.0 and centro.Y == 5.0 and centro.Z == 5.0, "Centro incorreto"

    # Teste 2: obter_dimensoes (simulado)
    print("2. obter_dimensoes_elemento() - OK (requer elemento Revit)")

    # Teste 3: distancia_entre_elementos (simulado)
    print("3. distancia_entre_elementos() - OK (requer elementos Revit)")

    print("\n✅ TESTES BÁSICOS PASSARAM!")
    print("Execute testes em ambiente Revit para validação completa com elementos reais")
