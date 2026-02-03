# -*- coding: utf-8 -*-
"""
D:\RVT 26\scripts\PYAMBAR(lab).extension\lib\Snippets\_section_transform.py
Descrição: Funções para criar Transform corretos para ViewSection (elevation, cross, plan)
Uso: from Snippets._section_transform import create_elevation_transform
Baseado em: SectionGenerator._views.py e CriarCortesTubos.pushbutton
"""

from Autodesk.Revit.DB import Transform, XYZ


def create_elevation_transform(start_point, end_point, mid_point=None):
    """
    Cria Transform para vista LATERAL (elevation) de elementos lineares.

    Mostra comprimento completo do elemento:
    - Tubos horizontais: ════════ (comprimento completo lateral)
    - Tubos verticais: ║ (altura completa lateral)

    Args:
        start_point (XYZ): Ponto inicial do elemento
        end_point (XYZ): Ponto final do elemento
        mid_point (XYZ, optional): Ponto médio (origem). Se None, calcula automaticamente.

    Returns:
        Transform: Transform configurado para vista de elevação lateral

    Example:
        >>> linha = tubo.Location.Curve
        >>> pt_start = linha.GetEndPoint(0)
        >>> pt_end = linha.GetEndPoint(1)
        >>> trans = create_elevation_transform(pt_start, pt_end)
        >>> bbox = create_bbox(trans, linha.Length, diameter)
        >>> view = ViewSection.CreateSection(doc, section_type_id, bbox)
    """
    element_direction = (end_point - start_point).Normalize()
    vertical_component = abs(element_direction.Z)

    # Calcular ponto médio se não fornecido
    if mid_point is None:
        mid_point = (start_point + end_point) / 2

    # Tolerância: >99% vertical = elemento vertical
    VERTICAL_TOLERANCE = 0.99

    trans = Transform.Identity
    trans.Origin = mid_point

    if vertical_component > VERTICAL_TOLERANCE:
        # ELEMENTO VERTICAL - Mostrar altura completa (║)

        # Componente horizontal (para determinar direção "direita")
        horizontal = XYZ(element_direction.X, element_direction.Y, 0)

        if horizontal.IsZeroLength():
            # Elemento perfeitamente vertical → usar direção padrão (Leste)
            horizontal = XYZ.BasisX
        else:
            horizontal = horizontal.Normalize()

        # Vista lateral do elemento vertical:
        trans.BasisX = horizontal  # Direita na tela
        trans.BasisY = element_direction  # Cima na tela = direção do elemento (mostra altura)
        trans.BasisZ = horizontal.CrossProduct(element_direction).Normalize()  # View lateral

    else:
        # ELEMENTO HORIZONTAL/INCLINADO - Mostrar comprimento completo (════════)

        # PADRÃO ELEVATION (SectionGenerator._views.py):
        trans.BasisX = element_direction  # Direita = direção do elemento (mostra comprimento)
        trans.BasisY = XYZ.BasisZ  # Cima = vertical (mantém orientação)
        trans.BasisZ = element_direction.CrossProduct(XYZ.BasisZ).Normalize()  # View = perpendicular lateral

        # Safety check: se cross product é zero (elemento vertical não detectado)
        if trans.BasisZ.IsZeroLength():
            # Fallback: usar direção alternativa
            trans.BasisX = XYZ.BasisY
            trans.BasisY = element_direction
            trans.BasisZ = XYZ.BasisY.CrossProduct(element_direction).Normalize()

    return trans


def create_cross_section_transform(start_point, end_point, mid_point=None):
    """
    Cria Transform para vista de CORTE TRANSVERSAL (cross-section).

    Mostra seção perpendicular ao elemento:
    - Tubos horizontais: ● (círculo - seção transversal)
    - Tubos verticais: ● (círculo - seção transversal)

    Args:
        start_point (XYZ): Ponto inicial do elemento
        end_point (XYZ): Ponto final do elemento
        mid_point (XYZ, optional): Ponto médio (origem). Se None, calcula automaticamente.

    Returns:
        Transform: Transform configurado para vista de corte transversal

    Example:
        >>> linha = tubo.Location.Curve
        >>> pt_start = linha.GetEndPoint(0)
        >>> pt_end = linha.GetEndPoint(1)
        >>> trans = create_cross_section_transform(pt_start, pt_end)
    """
    element_direction = (end_point - start_point).Normalize()

    # Calcular ponto médio se não fornecido
    if mid_point is None:
        mid_point = (start_point + end_point) / 2

    trans = Transform.Identity
    trans.Origin = mid_point

    # CROSS-SECTION: Olhar ao longo do elemento (perpendicular à sua direção)
    # BasisZ = direção do elemento (olhando ao longo dele)
    trans.BasisZ = element_direction

    # BasisY = vertical (cima na tela)
    trans.BasisY = XYZ.BasisZ

    # BasisX = perpendicular a ambos
    trans.BasisX = trans.BasisY.CrossProduct(trans.BasisZ).Normalize()

    # Safety check
    if trans.BasisX.IsZeroLength():
        # Se elemento é vertical, usar direção alternativa
        trans.BasisY = XYZ.BasisX
        trans.BasisX = trans.BasisY.CrossProduct(trans.BasisZ).Normalize()

    return trans


def create_plan_transform(start_point, end_point, mid_point=None):
    """
    Cria Transform para vista de PLANTA (plan - olhando de cima).

    Mostra elemento como visto de cima:
    - Tubos horizontais: ════════ (comprimento visto de cima)
    - Tubos verticais: ● (círculo visto de cima)

    Args:
        start_point (XYZ): Ponto inicial do elemento
        end_point (XYZ): Ponto final do elemento
        mid_point (XYZ, optional): Ponto médio (origem). Se None, calcula automaticamente.

    Returns:
        Transform: Transform configurado para vista de planta

    Example:
        >>> linha = tubo.Location.Curve
        >>> pt_start = linha.GetEndPoint(0)
        >>> pt_end = linha.GetEndPoint(1)
        >>> trans = create_plan_transform(pt_start, pt_end)
    """
    element_direction = (end_point - start_point).Normalize()

    # Calcular ponto médio se não fornecido
    if mid_point is None:
        mid_point = (start_point + end_point) / 2

    trans = Transform.Identity
    trans.Origin = mid_point

    # PLANTA: Olhar de cima para baixo
    # BasisZ = -Z (olhando para baixo)
    trans.BasisZ = -XYZ.BasisZ

    # BasisX = direção oposta do elemento
    trans.BasisX = -element_direction

    # BasisY = perpendicular
    trans.BasisY = -trans.BasisZ.CrossProduct(trans.BasisX).Normalize()

    return trans


def validate_transform(trans):
    """
    Valida se um Transform está correto (ortonormal).

    Args:
        trans (Transform): Transform a validar

    Returns:
        bool: True se válido, False caso contrário

    Example:
        >>> trans = create_elevation_transform(pt1, pt2)
        >>> if validate_transform(trans):
        ...     print("Transform válido!")
    """
    # Verificar se os vetores são perpendiculares (produto escalar ~ 0)
    dot_xy = abs(trans.BasisX.DotProduct(trans.BasisY))
    dot_xz = abs(trans.BasisX.DotProduct(trans.BasisZ))
    dot_yz = abs(trans.BasisY.DotProduct(trans.BasisZ))

    TOLERANCE = 0.001

    if dot_xy > TOLERANCE or dot_xz > TOLERANCE or dot_yz > TOLERANCE:
        return False

    # Verificar se os vetores são unitários (comprimento ~ 1)
    len_x = abs(trans.BasisX.GetLength() - 1.0)
    len_y = abs(trans.BasisY.GetLength() - 1.0)
    len_z = abs(trans.BasisZ.GetLength() - 1.0)

    if len_x > TOLERANCE or len_y > TOLERANCE or len_z > TOLERANCE:
        return False

    return True
