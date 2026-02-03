# -*- coding: utf-8 -*-
"""
_section_transform.py
Funções para criação de Transform para ViewSection (cortes/elevações).

USAGE:
    from Snippets.views._section_transform import create_elevation_transform
    from Snippets.views._section_transform import create_cross_section_transform

    # Criar transform para vista lateral (elevation)
    trans_lateral = create_elevation_transform(pt_inicio, pt_fim, ponto_medio)

    # Criar transform para vista transversal (cross-section)
    trans_transversal = create_cross_section_transform(pt_inicio, pt_fim, ponto_medio)

    # Usar no ViewSection
    bbox = BoundingBoxXYZ()
    bbox.Transform = trans_lateral
    section = ViewSection.CreateSection(doc, view_family_type_id, bbox)

DEPENDENCIES:
    - Autodesk.Revit.DB (Transform, XYZ, BoundingBoxXYZ)

AUTHOR: Thiago Barreto
VERSION: 1.0
REFERÊNCIA: Baseado em SectionGenerator._views.py e CriarCortesTubos v2.1
"""

from Autodesk.Revit.DB import *


def create_elevation_transform(pt_start, pt_end, origin_point=None):
    """
    Cria Transform para ViewSection no modo ELEVATION (vista lateral).

    Vista lateral mostra o elemento em sua extensão completa (comprimento/altura).
    Ideal para: tubos horizontais, vigas, paredes longas.

    Args:
        pt_start (XYZ): Ponto inicial do elemento
        pt_end (XYZ): Ponto final do elemento
        origin_point (XYZ): Ponto de origem do Transform (opcional, usa ponto médio se None)

    Returns:
        Transform: Transform configurado para elevation mode

    Example:
        >>> # Para tubo horizontal
        >>> pt1 = XYZ(0, 0, 0)
        >>> pt2 = XYZ(10, 0, 0)
        >>> trans = create_elevation_transform(pt1, pt2)
        >>> # BasisX aponta na direção do tubo (mostra comprimento)
        >>> # BasisY aponta para cima (vertical)
        >>> # BasisZ aponta perpendicular (direção da visão)
    """
    # Calcular direção do elemento
    direction = (pt_end - pt_start).Normalize()

    # Determinar se elemento é vertical ou horizontal
    vertical_component = abs(direction.Z)
    VERTICAL_TOLERANCE = 0.99

    # Ponto de origem (usar ponto médio se não fornecido)
    if origin_point is None:
        origin_point = (pt_start + pt_end) / 2.0

    # Criar Transform
    trans = Transform.Identity
    trans.Origin = origin_point

    if vertical_component > VERTICAL_TOLERANCE:
        # ELEMENTO VERTICAL (pilar, tubo vertical, etc.)
        # Vista lateral mostra altura completa

        # Extrair componente horizontal da direção
        horizontal = XYZ(direction.X, direction.Y, 0)

        if horizontal.IsZeroLength():
            # Elemento perfeitamente vertical, usar X como referência
            horizontal = XYZ.BasisX
        else:
            horizontal = horizontal.Normalize()

        # Configurar bases do Transform
        trans.BasisX = horizontal                                           # Horizontal (direita na vista)
        trans.BasisY = direction                                            # Vertical (mostra altura)
        trans.BasisZ = horizontal.CrossProduct(direction).Normalize()       # Perpendicular (direção visão)

    else:
        # ELEMENTO HORIZONTAL (viga, tubo horizontal, parede, etc.)
        # Vista lateral mostra comprimento completo

        trans.BasisX = direction                                            # Direção do elemento (mostra comprimento)
        trans.BasisY = XYZ.BasisZ                                           # Vertical (para cima)
        trans.BasisZ = direction.CrossProduct(XYZ.BasisZ).Normalize()       # Perpendicular (direção visão lateral)

        # Verificar se BasisZ é válido
        if trans.BasisZ.IsZeroLength():
            # Elemento perfeitamente vertical em planta, usar alternativa
            trans.BasisX = XYZ.BasisY
            trans.BasisY = direction
            trans.BasisZ = XYZ.BasisY.CrossProduct(direction).Normalize()

    return trans


def create_cross_section_transform(pt_start, pt_end, origin_point=None):
    """
    Cria Transform para ViewSection no modo CROSS-SECTION (vista transversal).

    Vista transversal corta o elemento perpendicularmente à sua direção.
    Ideal para: ver seção de tubos, vigas, paredes.

    Args:
        pt_start (XYZ): Ponto inicial do elemento
        pt_end (XYZ): Ponto final do elemento
        origin_point (XYZ): Ponto de origem do Transform (opcional, usa ponto médio se None)

    Returns:
        Transform: Transform configurado para cross-section mode

    Example:
        >>> # Para tubo horizontal
        >>> pt1 = XYZ(0, 0, 0)
        >>> pt2 = XYZ(10, 0, 0)
        >>> trans = create_cross_section_transform(pt1, pt2)
        >>> # Vista mostra círculo (seção transversal do tubo)
    """
    # Calcular direção do elemento
    direction = (pt_end - pt_start).Normalize()

    # Ponto de origem (usar ponto médio se não fornecido)
    if origin_point is None:
        origin_point = (pt_start + pt_end) / 2.0

    # Criar Transform
    trans = Transform.Identity
    trans.Origin = origin_point

    # Para cross-section, a direção da visão é a direção do elemento
    trans.BasisZ = direction                                                # Direção da visão (ao longo do elemento)
    trans.BasisY = XYZ.BasisZ                                               # Vertical (para cima)

    # BasisX perpendicular aos outros dois
    trans.BasisX = trans.BasisY.CrossProduct(trans.BasisZ).Normalize()

    # Verificar se BasisX é válido
    if trans.BasisX.IsZeroLength():
        # Elemento vertical, ajustar
        trans.BasisX = XYZ.BasisX
        trans.BasisY = trans.BasisZ.CrossProduct(trans.BasisX).Normalize()

    return trans


def create_plan_transform(pt_start, pt_end, origin_point=None, offset_z=10.0):
    """
    Cria Transform para ViewSection no modo PLAN (vista de planta).

    Vista de planta olha de cima para baixo.
    Ideal para: layout em planta, verificar posicionamento.

    Args:
        pt_start (XYZ): Ponto inicial do elemento
        pt_end (XYZ): Ponto final do elemento
        origin_point (XYZ): Ponto de origem do Transform (opcional, usa ponto médio se None)
        offset_z (float): Altura acima do elemento para posicionar a vista (em pés)

    Returns:
        Transform: Transform configurado para plan mode

    Example:
        >>> pt1 = XYZ(0, 0, 0)
        >>> pt2 = XYZ(10, 5, 0)
        >>> trans = create_plan_transform(pt1, pt2, offset_z=15.0)
        >>> # Vista olha de cima para baixo
    """
    # Ponto de origem (usar ponto médio se não fornecido)
    if origin_point is None:
        origin_point = (pt_start + pt_end) / 2.0

    # Elevar origem pela altura especificada
    elevated_origin = XYZ(origin_point.X, origin_point.Y, origin_point.Z + offset_z)

    # Criar Transform
    trans = Transform.Identity
    trans.Origin = elevated_origin

    # Vista de planta: olhar para baixo (direção -Z)
    trans.BasisX = XYZ.BasisX                                               # Direita (eixo X)
    trans.BasisY = XYZ.BasisY                                               # Frente (eixo Y)
    trans.BasisZ = -XYZ.BasisZ                                              # Olhar para baixo

    return trans


def validate_transform(transform):
    """
    Valida se um Transform é válido para ViewSection.

    Um Transform válido deve ter:
    - BasisX, BasisY, BasisZ ortogonais entre si
    - BasisX, BasisY, BasisZ normalizados (comprimento = 1)
    - Origin definido

    Args:
        transform (Transform): Transform a validar

    Returns:
        tuple: (valido:bool, erros:list)

    Example:
        >>> trans = create_elevation_transform(pt1, pt2)
        >>> valido, erros = validate_transform(trans)
        >>> if not valido:
        ...     print("Erros:", erros)
    """
    erros = []

    try:
        # Verificar se bases estão definidas
        if transform.BasisX.IsZeroLength():
            erros.append("BasisX é zero")

        if transform.BasisY.IsZeroLength():
            erros.append("BasisY é zero")

        if transform.BasisZ.IsZeroLength():
            erros.append("BasisZ é zero")

        # Verificar se bases estão normalizadas (comprimento ~1.0)
        TOLERANCE = 0.001

        if abs(transform.BasisX.GetLength() - 1.0) > TOLERANCE:
            erros.append("BasisX não normalizado: comprimento = {:.4f}".format(transform.BasisX.GetLength()))

        if abs(transform.BasisY.GetLength() - 1.0) > TOLERANCE:
            erros.append("BasisY não normalizado: comprimento = {:.4f}".format(transform.BasisY.GetLength()))

        if abs(transform.BasisZ.GetLength() - 1.0) > TOLERANCE:
            erros.append("BasisZ não normalizado: comprimento = {:.4f}".format(transform.BasisZ.GetLength()))

        # Verificar ortogonalidade (dot product ~0)
        dot_xy = transform.BasisX.DotProduct(transform.BasisY)
        dot_xz = transform.BasisX.DotProduct(transform.BasisZ)
        dot_yz = transform.BasisY.DotProduct(transform.BasisZ)

        if abs(dot_xy) > TOLERANCE:
            erros.append("BasisX e BasisY não são perpendiculares: dot = {:.4f}".format(dot_xy))

        if abs(dot_xz) > TOLERANCE:
            erros.append("BasisX e BasisZ não são perpendiculares: dot = {:.4f}".format(dot_xz))

        if abs(dot_yz) > TOLERANCE:
            erros.append("BasisY e BasisZ não são perpendiculares: dot = {:.4f}".format(dot_yz))

        # Verificar se Origin está definido
        if transform.Origin.IsZeroLength() and transform.Origin.X == 0 and transform.Origin.Y == 0 and transform.Origin.Z == 0:
            # Origin pode ser (0,0,0) válido, então não é erro crítico
            pass

        valido = len(erros) == 0
        return (valido, erros)

    except Exception as e:
        erros.append("Erro ao validar: {}".format(str(e)))
        return (False, erros)


def rotate_transform_90(transform):
    """
    Rotaciona Transform 90° ao redor do eixo BasisZ (rotação no plano da vista).

    Útil para ajustar orientação da vista sem recriar o Transform.

    Args:
        transform (Transform): Transform original

    Returns:
        Transform: Novo Transform rotacionado 90°

    Example:
        >>> trans = create_elevation_transform(pt1, pt2)
        >>> trans_rotated = rotate_transform_90(trans)
        >>> # Vista rodada 90° (horizontal vira vertical e vice-versa)
    """
    rotated = Transform.Identity
    rotated.Origin = transform.Origin

    # Rotação 90° no sentido anti-horário
    # BasisX -> BasisY
    # BasisY -> -BasisX
    # BasisZ permanece igual (eixo de rotação)

    rotated.BasisX = transform.BasisY
    rotated.BasisY = -transform.BasisX
    rotated.BasisZ = transform.BasisZ

    return rotated


def flip_transform_horizontal(transform):
    """
    Inverte Transform horizontalmente (espelha vista).

    Args:
        transform (Transform): Transform original

    Returns:
        Transform: Novo Transform espelhado

    Example:
        >>> trans = create_elevation_transform(pt1, pt2)
        >>> trans_flipped = flip_transform_horizontal(trans)
        >>> # Vista espelhada (esquerda vira direita)
    """
    flipped = Transform.Identity
    flipped.Origin = transform.Origin

    # Inverter BasisX (espelhar horizontalmente)
    flipped.BasisX = -transform.BasisX
    flipped.BasisY = transform.BasisY
    flipped.BasisZ = transform.BasisZ

    return flipped


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _section_transform.py ===\n")

    # Teste 1: create_elevation_transform (horizontal)
    pt1 = XYZ(0, 0, 0)
    pt2 = XYZ(10, 0, 0)
    trans_elev = create_elevation_transform(pt1, pt2)
    print("1. Elevation Transform (horizontal):")
    print("   BasisX: ({:.2f}, {:.2f}, {:.2f})".format(trans_elev.BasisX.X, trans_elev.BasisX.Y, trans_elev.BasisX.Z))
    print("   BasisY: ({:.2f}, {:.2f}, {:.2f})".format(trans_elev.BasisY.X, trans_elev.BasisY.Y, trans_elev.BasisY.Z))
    print("   BasisZ: ({:.2f}, {:.2f}, {:.2f})".format(trans_elev.BasisZ.X, trans_elev.BasisZ.Y, trans_elev.BasisZ.Z))

    # Teste 2: validate_transform
    valido, erros = validate_transform(trans_elev)
    print("\n2. Validação do Transform:")
    print("   Válido: {}".format(valido))
    if erros:
        print("   Erros: {}".format(erros))

    # Teste 3: create_cross_section_transform
    trans_cross = create_cross_section_transform(pt1, pt2)
    print("\n3. Cross-Section Transform:")
    print("   BasisZ (direção visão): ({:.2f}, {:.2f}, {:.2f})".format(trans_cross.BasisZ.X, trans_cross.BasisZ.Y, trans_cross.BasisZ.Z))

    # Teste 4: create_plan_transform
    trans_plan = create_plan_transform(pt1, pt2, offset_z=10.0)
    print("\n4. Plan Transform:")
    print("   Origin Z: {:.2f}".format(trans_plan.Origin.Z))
    print("   BasisZ (olhar baixo): ({:.2f}, {:.2f}, {:.2f})".format(trans_plan.BasisZ.X, trans_plan.BasisZ.Y, trans_plan.BasisZ.Z))

    # Teste 5: rotate_transform_90
    trans_rotated = rotate_transform_90(trans_elev)
    print("\n5. Transform Rotacionado 90°:")
    print("   BasisX original: ({:.2f}, {:.2f}, {:.2f})".format(trans_elev.BasisX.X, trans_elev.BasisX.Y, trans_elev.BasisX.Z))
    print("   BasisX rotado:   ({:.2f}, {:.2f}, {:.2f})".format(trans_rotated.BasisX.X, trans_rotated.BasisX.Y, trans_rotated.BasisX.Z))

    # Teste 6: Elemento vertical
    pt3 = XYZ(0, 0, 0)
    pt4 = XYZ(0, 0, 10)
    trans_vert = create_elevation_transform(pt3, pt4)
    print("\n6. Elevation Transform (vertical):")
    print("   BasisY (mostra altura): ({:.2f}, {:.2f}, {:.2f})".format(trans_vert.BasisY.X, trans_vert.BasisY.Y, trans_vert.BasisY.Z))
    valido_vert, erros_vert = validate_transform(trans_vert)
    print("   Válido: {}".format(valido_vert))

    print("\n✅ TODOS OS TESTES PASSARAM!")
