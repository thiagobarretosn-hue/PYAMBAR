# -*- coding: utf-8 -*-
"""Biblioteca compartilhada para operações MEP.

Funções reutilizáveis para trabalhar com elementos MEP, conectores,
e sistemas. Inspirado em pyRevitMEP (Cyril Waechter).
"""

from math import pi, degrees, sqrt
from Autodesk.Revit.DB import *
from Autodesk.Revit import Exceptions


# ==================== CONNECTOR UTILITIES ====================

def get_connector_manager(element):
    """Retorna ConnectorManager de qualquer elemento MEP.
    
    Funciona com:
    - MEPCurve (Pipe, Duct, CableTray, Conduit)
    - FamilyInstance (equipamentos MEP, fittings)
    - FlexPipe, FlexDuct
    
    Args:
        element: Elemento do Revit
        
    Returns:
        ConnectorManager
        
    Raises:
        AttributeError: Se elemento não possui ConnectorManager
        
    Examples:
        >>> cm = get_connector_manager(pipe)
        >>> for conn in cm.Connectors:
        ...     print(conn.Origin)
    """
    # Tenta como MEPCurve (pipes, ducts, cable trays, conduits)
    if hasattr(element, 'ConnectorManager'):
        return element.ConnectorManager
    
    # Tenta como FamilyInstance (equipamentos, fittings)
    if hasattr(element, 'MEPModel'):
        mep_model = element.MEPModel
        if mep_model and hasattr(mep_model, 'ConnectorManager'):
            return mep_model.ConnectorManager
    
    raise AttributeError(
        "Elemento '{}' (ID: {}) não possui ConnectorManager".format(
            element.Name if hasattr(element, 'Name') else 'Unknown',
            element.Id
        )
    )


def get_all_connectors(element):
    """Retorna todos os conectores de um elemento como lista.
    
    Args:
        element: Elemento MEP
        
    Returns:
        list: Lista de Connector objects
    """
    cm = get_connector_manager(element)
    return list(cm.Connectors)


def get_unused_connectors(element):
    """Retorna apenas conectores não usados de um elemento.
    
    Args:
        element: Elemento MEP
        
    Returns:
        list: Lista de conectores não conectados
    """
    cm = get_connector_manager(element)
    return list(cm.UnusedConnectors)


def get_connector_closest_to(connectors, xyz_point):
    """Retorna o conector mais próximo de um ponto.
    
    Args:
        connectors: ConnectorSet, lista, ou iterável de conectores
        xyz_point: Ponto XYZ para comparação
        
    Returns:
        Connector: Conector mais próximo ou None se vazio
        
    Examples:
        >>> point = XYZ(0, 0, 0)
        >>> closest = get_connector_closest_to(pipe.ConnectorManager.Connectors, point)
    """
    min_distance = float("inf")
    closest_connector = None
    
    for connector in connectors:
        distance = connector.Origin.DistanceTo(xyz_point)
        if distance < min_distance:
            min_distance = distance
            closest_connector = connector
    
    return closest_connector


def find_closest_connector_pair(element1, element2, unused_only=True):
    """Encontra o par de conectores mais próximos entre dois elementos.
    
    Args:
        element1: Primeiro elemento MEP
        element2: Segundo elemento MEP
        unused_only: Se True, considera apenas conectores não usados
        
    Returns:
        tuple: (connector1, connector2, distance) ou (None, None, inf)
    """
    cm1 = get_connector_manager(element1)
    cm2 = get_connector_manager(element2)
    
    # Selecionar tipo de conectores
    connectors1 = cm1.UnusedConnectors if unused_only else cm1.Connectors
    connectors2 = cm2.UnusedConnectors if unused_only else cm2.Connectors
    
    min_distance = float("inf")
    closest_pair = (None, None)
    
    for conn1 in connectors1:
        for conn2 in connectors2:
            distance = conn1.Origin.DistanceTo(conn2.Origin)
            if distance < min_distance:
                min_distance = distance
                closest_pair = (conn1, conn2)
    
    return closest_pair[0], closest_pair[1], min_distance


def get_connector_direction(connector):
    """Retorna o vetor de direção de um conector.
    
    Args:
        connector: Connector object
        
    Returns:
        XYZ: Vetor direção (normalizado)
    """
    try:
        return connector.CoordinateSystem.BasisZ
    except AttributeError:
        return None


def calculate_connector_angle(conn1, conn2, in_degrees=False):
    """Calcula ângulo entre dois conectores.
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        in_degrees: Se True, retorna em graus ao invés de radianos
        
    Returns:
        float: Ângulo entre conectores (radianos ou graus)
        None: Se não conseguir calcular
    """
    try:
        dir1 = get_connector_direction(conn1)
        dir2 = get_connector_direction(conn2)
        
        if dir1 is None or dir2 is None:
            return None
        
        angle = dir1.AngleTo(dir2)
        
        if in_degrees:
            return degrees(angle)
        return angle
    
    except Exception:
        return None


def are_connectors_aligned(conn1, conn2, tolerance_degrees=5.0):
    """Verifica se dois conectores estão alinhados.
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        tolerance_degrees: Tolerância de ângulo em graus
        
    Returns:
        bool: True se alinhados (dentro da tolerância)
    """
    angle = calculate_connector_angle(conn1, conn2, in_degrees=True)
    
    if angle is None:
        return False
    
    # Alinhados se ângulo próximo de 0° ou 180°
    return angle < tolerance_degrees or angle > (180.0 - tolerance_degrees)


def get_connector_domain_name(connector):
    """Retorna nome legível do domínio do conector.
    
    Args:
        connector: Connector object
        
    Returns:
        str: Nome do domínio em português
    """
    domain_names = {
        Domain.DomainHvac: "HVAC (Ar Condicionado)",
        Domain.DomainPiping: "Hidráulico (Tubulação)",
        Domain.DomainElectrical: "Elétrico",
        Domain.DomainCableTrayConduit: "Bandeja/Eletroduto"
    }
    
    try:
        return domain_names.get(connector.Domain, "Desconhecido")
    except:
        return "Indefinido"


def validate_connector_compatibility(conn1, conn2):
    """Valida se dois conectores podem ser conectados.
    
    Verifica:
    - Mesmo domínio
    - Diâmetros compatíveis (com tolerância)
    - Não já conectados entre si
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        
    Returns:
        tuple: (bool is_compatible, str error_message)
    """
    # Verificar domínio
    try:
        if conn1.Domain != conn2.Domain:
            return False, "Conectores de domínios diferentes ({} vs {})".format(
                get_connector_domain_name(conn1),
                get_connector_domain_name(conn2)
            )
    except:
        pass  # Ignorar se não conseguir verificar domínio
    
    # Verificar se já conectados
    if conn1.IsConnected and conn2.IsConnected:
        for ref in conn1.AllRefs:
            if ref.Owner.Id == conn2.Owner.Id:
                return False, "Conectores já estão conectados entre si"
    
    # Verificar diâmetros (com 10% de tolerância)
    try:
        diam1 = conn1.Radius * 2
        diam2 = conn2.Radius * 2
        
        if abs(diam1 - diam2) > max(diam1, diam2) * 0.1:
            return False, "Diâmetros incompatíveis ({:.2f}\" vs {:.2f}\")".format(
                diam1 * 12, diam2 * 12  # Converter pés para polegadas
            )
    except:
        pass  # Ignorar se não conseguir verificar diâmetros
    
    return True, ""


# ==================== ELEMENT UTILITIES ====================

def get_element_endpoints(element):
    """Retorna pontos inicial e final de um MEPCurve.
    
    Args:
        element: MEPCurve (Pipe, Duct, etc)
        
    Returns:
        tuple: (XYZ start, XYZ end) ou (None, None)
    """
    location = element.Location
    
    if isinstance(location, LocationCurve):
        curve = location.Curve
        return curve.GetEndPoint(0), curve.GetEndPoint(1)
    
    return None, None


def get_element_midpoint(element):
    """Retorna ponto médio de um MEPCurve.
    
    Args:
        element: MEPCurve
        
    Returns:
        XYZ: Ponto médio ou None
    """
    start, end = get_element_endpoints(element)
    
    if start and end:
        return XYZ(
            (start.X + end.X) / 2.0,
            (start.Y + end.Y) / 2.0,
            (start.Z + end.Z) / 2.0
        )
    
    return None


def get_element_length(element):
    """Retorna comprimento de um MEPCurve.
    
    Args:
        element: MEPCurve
        
    Returns:
        float: Comprimento em pés ou None
    """
    location = element.Location
    
    if isinstance(location, LocationCurve):
        return location.Curve.Length
    
    return None


def move_element(element, translation_vector):
    """Move um elemento por um vetor de translação.
    
    Args:
        element: Elemento a mover
        translation_vector: XYZ vetor de movimento
        
    Returns:
        bool: True se sucesso
    """
    try:
        location = element.Location
        
        if isinstance(location, LocationPoint):
            success = location.Move(translation_vector)
            return success
        
        elif isinstance(location, LocationCurve):
            success = location.Move(translation_vector)
            return success
        
        return False
    
    except Exception:
        return False


def rotate_element(element, axis_line, angle_radians):
    """Rotaciona um elemento em torno de um eixo.
    
    Args:
        element: Elemento a rotacionar
        axis_line: Line definindo eixo de rotação
        angle_radians: Ângulo em radianos
        
    Returns:
        bool: True se sucesso
    """
    try:
        location = element.Location
        
        if isinstance(location, (LocationPoint, LocationCurve)):
            success = location.Rotate(axis_line, angle_radians)
            return success
        
        return False
    
    except Exceptions.ArgumentsInconsistentException:
        # Geometria inválida para rotação
        return False
    
    except Exception:
        return False


# ==================== FITTING CREATION ====================

def create_elbow_fitting(conn1, conn2, doc):
    """Cria cotovelo entre dois conectores.
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        doc: Document
        
    Returns:
        FamilyInstance: Cotovelo criado ou None
    """
    try:
        fitting = doc.Create.NewElbowFitting(conn1, conn2)
        return fitting
    except Exceptions.InvalidOperationException:
        return None
    except Exception:
        return None


def create_tee_fitting(conn1, conn2, conn3, doc):
    """Cria tê entre três conectores.
    
    Args:
        conn1: Primeiro conector (main)
        conn2: Segundo conector (main)
        conn3: Terceiro conector (branch)
        doc: Document
        
    Returns:
        FamilyInstance: Tê criado ou None
    """
    try:
        fitting = doc.Create.NewTeeFitting(conn1, conn2, conn3)
        return fitting
    except Exceptions.InvalidOperationException:
        return None
    except Exception:
        return None


def create_union_fitting(conn1, conn2, doc):
    """Cria união entre dois conectores.
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        doc: Document
        
    Returns:
        FamilyInstance: União criada ou None
    """
    try:
        fitting = doc.Create.NewUnionFitting(conn1, conn2)
        return fitting
    except Exceptions.InvalidOperationException:
        return None
    except Exception:
        return None


def create_transition_fitting(conn1, conn2, doc):
    """Cria transição entre conectores de diâmetros diferentes.
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        doc: Document
        
    Returns:
        FamilyInstance: Transição criada ou None
    """
    try:
        fitting = doc.Create.NewTransitionFitting(conn1, conn2)
        return fitting
    except Exceptions.InvalidOperationException:
        return None
    except Exception:
        return None


def create_appropriate_fitting(conn1, conn2, doc):
    """Cria fitting apropriado baseado no ângulo entre conectores.
    
    Decide automaticamente entre:
    - Elbow (10° a 170°)
    - Union/Direct (< 10° ou > 170°)
    
    Args:
        conn1: Primeiro conector
        conn2: Segundo conector
        doc: Document
        
    Returns:
        FamilyInstance ou None: Fitting criado, ou None se conexão direta
    """
    angle = calculate_connector_angle(conn1, conn2)
    
    if angle is None:
        # Tentar conexão direta
        try:
            conn1.ConnectTo(conn2)
            return None
        except:
            return None
    
    # Cotovelo: 10° a 170° (0.175 a 2.967 radianos)
    if 0.175 < angle < 2.967:
        fitting = create_elbow_fitting(conn1, conn2, doc)
        if fitting:
            return fitting
    
    # União: quase paralelo ou oposto
    fitting = create_union_fitting(conn1, conn2, doc)
    if fitting:
        return fitting
    
    # Fallback: conexão direta
    try:
        conn1.ConnectTo(conn2)
    except:
        pass
    
    return None


# ==================== GEOMETRY UTILITIES ====================

def calculate_rotation_axis(direction1, direction2):
    """Calcula eixo de rotação entre dois vetores.
    
    Args:
        direction1: XYZ primeiro vetor
        direction2: XYZ segundo vetor
        
    Returns:
        XYZ: Vetor eixo de rotação ou None
    """
    try:
        # Se paralelos mesma direção, usar perpendicular
        angle = direction1.AngleTo(direction2)
        
        if angle == 0:
            # Usar eixo perpendicular arbitrário
            if abs(direction1.Z) < 0.9:
                return XYZ.BasisZ
            else:
                return XYZ.BasisX
        
        # Cross product para eixo perpendicular
        axis = direction1.CrossProduct(direction2)
        
        # Normalizar
        length = axis.GetLength()
        if length < 0.001:
            return None
        
        return axis.Normalize()
    
    except:
        return None


def points_distance_3d(point1, point2):
    """Calcula distância 3D entre dois pontos.
    
    Args:
        point1: XYZ primeiro ponto
        point2: XYZ segundo ponto
        
    Returns:
        float: Distância em pés
    """
    return point1.DistanceTo(point2)


def points_distance_horizontal(point1, point2):
    """Calcula distância horizontal (ignorando Z) entre pontos.
    
    Args:
        point1: XYZ primeiro ponto
        point2: XYZ segundo ponto
        
    Returns:
        float: Distância horizontal em pés
    """
    dx = point2.X - point1.X
    dy = point2.Y - point1.Y
    return sqrt(dx * dx + dy * dy)


# ==================== TYPE/SYSTEM UTILITIES ====================

def get_mep_system(element):
    """Retorna sistema MEP de um elemento.
    
    Args:
        element: Elemento MEP
        
    Returns:
        MEPSystem ou None
    """
    try:
        # Para MEPCurve
        if hasattr(element, 'MEPSystem'):
            return element.MEPSystem
        
        # Para FamilyInstance
        if hasattr(element, 'MEPModel'):
            mep_model = element.MEPModel
            if mep_model and hasattr(mep_model, 'MEPSystem'):
                return mep_model.MEPSystem
    
    except:
        pass
    
    return None


def get_element_type_name(element):
    """Retorna nome do tipo do elemento.
    
    Args:
        element: Elemento qualquer
        
    Returns:
        str: Nome do tipo ou "Unknown"
    """
    try:
        element_type = element.Document.GetElement(element.GetTypeId())
        if element_type:
            return element_type.Name
    except:
        pass
    
    return "Unknown"


# ==================== VALIDATION UTILITIES ====================

def is_mep_element(element):
    """Verifica se elemento é MEP.
    
    Args:
        element: Elemento do Revit
        
    Returns:
        bool: True se é MEP
    """
    try:
        get_connector_manager(element)
        return True
    except AttributeError:
        return False


def can_elements_connect(element1, element2):
    """Verifica se dois elementos podem ser conectados.
    
    Args:
        element1: Primeiro elemento
        element2: Segundo elemento
        
    Returns:
        tuple: (bool can_connect, str reason)
    """
    # Verificar se são MEP
    if not is_mep_element(element1):
        return False, "Primeiro elemento não é MEP"
    
    if not is_mep_element(element2):
        return False, "Segundo elemento não é MEP"
    
    # Verificar se têm conectores disponíveis
    unused1 = get_unused_connectors(element1)
    unused2 = get_unused_connectors(element2)
    
    if not unused1:
        return False, "Primeiro elemento não tem conectores disponíveis"
    
    if not unused2:
        return False, "Segundo elemento não tem conectores disponíveis"
    
    # Encontrar conectores mais próximos e validar
    conn1, conn2, distance = find_closest_connector_pair(element1, element2)
    
    if conn1 is None or conn2 is None:
        return False, "Não foi possível encontrar conectores compatíveis"
    
    # Validar compatibilidade
    compatible, error_msg = validate_connector_compatibility(conn1, conn2)
    
    return compatible, error_msg if not compatible else ""