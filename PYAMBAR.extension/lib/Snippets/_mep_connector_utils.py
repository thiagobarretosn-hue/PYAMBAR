# -*- coding: utf-8 -*-
"""
Nome do arquivo: _mep_connector_utils.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
Utilitários para trabalhar com conectores de elementos MEP (tubos, dutos, bandejas).
Funções para obter ConnectorManager, buscar conectores por proximidade e conectar elementos.

Autor: Thiago Barreto Sobral Nunes
Data: 23.10.2025
Versão: 2.0

Funções:
- get_connector_manager(element): Obtém ConnectorManager de elemento MEP
- get_connector_closest_to(connectors, xyz_point): Retorna conector mais próximo do ponto
- get_all_connectors(element): Retorna todos os conectores (usados e não usados)
- get_unused_connectors(element): Retorna apenas conectores não conectados
- connect_elements(doc, moved_element, moved_connector, target_connector): Conecta elementos
- MEPElementFilter: Classe de filtro para seleção de elementos MEP
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from math import pi, sqrt
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ISelectionFilter
from Autodesk.Revit.Exceptions import ArgumentsInconsistentException


def get_connector_manager(element):
    """
    Obtém o ConnectorManager de um elemento MEP.
    
    Args:
        element (Element): Elemento do Revit (Pipe, Duct, FamilyInstance, etc.)
    
    Returns:
        ConnectorManager: Manager de conectores do elemento
        
    Raises:
        AttributeError: Se elemento não possui ConnectorManager
    """
    if hasattr(element, 'ConnectorManager'):
        return element.ConnectorManager
    
    if hasattr(element, 'MEPModel'):
        if element.MEPModel and hasattr(element.MEPModel, 'ConnectorManager'):
            return element.MEPModel.ConnectorManager
    
    raise AttributeError("Elemento '{}' (Id: {}) não possui ConnectorManager".format(
        element.Name if hasattr(element, 'Name') else type(element).__name__,
        element.Id
    ))


def get_connector_closest_to(connectors, xyz_point):
    """
    Retorna o conector mais próximo de um ponto 3D.
    
    Args:
        connectors (ConnectorSet ou iterable): Coleção de conectores
        xyz_point (XYZ): Ponto de referência no espaço 3D
    
    Returns:
        Connector: Conector mais próximo do ponto, ou None se coleção vazia
    """
    min_distance = float("inf")
    closest_connector = None
    
    for connector in connectors:
        distance = connector.Origin.DistanceTo(xyz_point)
        if distance < min_distance:
            min_distance = distance
            closest_connector = connector
    
    return closest_connector


def get_all_connectors(element):
    """
    Retorna TODOS os conectores de um elemento (usados e não usados).
    
    Args:
        element (Element): Elemento MEP
    
    Returns:
        list: Lista de conectores (Connector objects)
    """
    try:
        cm = get_connector_manager(element)
        return list(cm.Connectors)
    except AttributeError:
        return []


def get_unused_connectors(element):
    """
    Retorna apenas conectores NÃO conectados de um elemento.
    
    Args:
        element (Element): Elemento MEP
    
    Returns:
        list: Lista de conectores não utilizados
    """
    try:
        cm = get_connector_manager(element)
        return list(cm.UnusedConnectors)
    except AttributeError:
        return []


def disconnect_connector(connector):
    """
    Desconecta um conector de suas conexões atuais.
    
    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.
    
    Args:
        connector (Connector): Conector a ser desconectado
    
    Returns:
        bool: True se desconectado com sucesso ou já estava desconectado
        
    Example:
        >>> with Transaction(doc, "Desconectar") as t:
        ...     t.Start()
        ...     disconnect_connector(conn1)
        ...     t.Commit()
    """
    try:
        if connector.IsConnected:
            # Desconectar todas as referências conectadas
            refs = connector.AllRefs
            for ref in refs:
                if ref.Owner.Id != connector.Owner.Id:
                    connector.DisconnectFrom(ref)
        return True
    except Exception:
        return False


def connect_elements(moved_element, moved_connector, target_connector, tolerance=0.001, auto_disconnect=True):
    """
    Conecta dois elementos MEP rotacionando e movendo o primeiro até o segundo.
    
    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.
    
    Args:
        moved_element (Element): Elemento a ser movido e rotacionado
        moved_connector (Connector): Conector do elemento a mover
        target_connector (Connector): Conector do elemento alvo
        tolerance (float): Tolerância para comparação de ângulos (radianos)
        auto_disconnect (bool): Se True, desconecta conectores automaticamente antes de conectar
    
    Returns:
        bool: True se conectado com sucesso, False se houve erro
        
    Example:
        >>> with Transaction(doc, "Conectar") as t:
        ...     t.Start()
        ...     success = connect_elements(pipe1, conn1, conn2)
        ...     t.Commit()
    """
    # Desconectar conectores se necessário
    if auto_disconnect:
        disconnect_connector(moved_connector)
        disconnect_connector(target_connector)

    # Obter direções dos conectores
    moved_dir = moved_connector.CoordinateSystem.BasisZ
    target_dir = target_connector.CoordinateSystem.BasisZ
    moved_point = moved_connector.Origin

    # Calcular ângulo entre direções
    angle = moved_dir.AngleTo(target_dir)

    # Rotacionar se necessário (direções devem ser opostas para conexão)
    if abs(angle - pi) > tolerance:
        if abs(angle) < tolerance:
            # Mesma direção - rotacionar 180 graus no eixo Y
            vector = moved_connector.CoordinateSystem.BasisY
            rotation_angle = pi
        else:
            # Calcular eixo perpendicular usando produto vetorial
            vector = moved_dir.CrossProduct(target_dir)
            rotation_angle = angle - pi

        try:
            axis = Line.CreateBound(moved_point, moved_point + vector)
            moved_element.Location.Rotate(axis, rotation_angle)
        except ArgumentsInconsistentException:
            # Elemento não pode ser rotacionado (fixo, sem Location, etc)
            return False

    # Mover elemento para alinhar conectores
    translation = target_connector.Origin - moved_connector.Origin
    moved_element.Location.Move(translation)

    # Conectar logicamente os conectores
    moved_connector.ConnectTo(target_connector)

    return True


class MEPElementFilter(ISelectionFilter):
    """
    Filtro de seleção para elementos MEP com conectores.
    
    Permite selecionar apenas elementos que possuem ConnectorManager:
    - Pipes, Ducts, CableTray, Conduit
    - FamilyInstance com conectores MEP
    - Fittings (cotovelos, tês, uniões, etc.)
    
    Ignora automaticamente:
    - Isolamentos (InsulationLiningBase)
    - Elementos sem conectores
    """
    
    def AllowElement(self, elem):
        """Determina se elemento pode ser selecionado."""
        if isinstance(elem, InsulationLiningBase):
            return False
        
        try:
            get_connector_manager(elem)
            return True
        except AttributeError:
            return False
    
    def AllowReference(self, reference, position):
        """Permite referência ao elemento."""
        return True


def get_connector_info(connector):
    """
    Retorna informações detalhadas de um conector para debug.
    
    Args:
        connector (Connector): Conector a ser analisado
    
    Returns:
        dict: Dicionário com propriedades do conector
    """
    return {
        'Origin': connector.Origin,
        'Domain': str(connector.Domain),
        'Shape': str(connector.Shape),
        'IsConnected': connector.IsConnected,
        'ConnectorType': str(connector.ConnectorType),
        'Diameter': connector.Radius * 2 if hasattr(connector, 'Radius') else None,
        'Flow': connector.Flow if hasattr(connector, 'Flow') else None
    }


def connect_elements_no_rotate(moved_element, moved_connector, target_connector, auto_disconnect=True):
    """
    Conecta dois elementos MEP movendo o primeiro até o segundo SEM ROTACIONAR.
    Mantém a inclinação/orientação original do elemento movido.
    Similar ao comportamento do Move and Connect da Microdesk.

    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.

    Args:
        moved_element (Element): Elemento a ser movido (sem rotação)
        moved_connector (Connector): Conector do elemento a mover
        target_connector (Connector): Conector do elemento alvo
        auto_disconnect (bool): Se True, desconecta conectores automaticamente antes de conectar

    Returns:
        bool: True se conectado com sucesso, False se houve erro

    Example:
        >>> with Transaction(doc, "Conectar Sem Rotação") as t:
        ...     t.Start()
        ...     success = connect_elements_no_rotate(pipe1, conn1, conn2)
        ...     t.Commit()
    """
    try:
        # Desconectar conectores se necessário
        if auto_disconnect:
            disconnect_connector(moved_connector)
            disconnect_connector(target_connector)

        # Mover elemento para alinhar conectores (SEM ROTAÇÃO)
        # Apenas translação - mantém orientação original
        translation = target_connector.Origin - moved_connector.Origin
        moved_element.Location.Move(translation)

        # Conectar logicamente os conectores
        moved_connector.ConnectTo(target_connector)

        return True

    except Exception:
        return False


def _derive_slope_from_neighbors(target_connector, default):
    """Fallback: deriva slope do fitting alvo quando BasisZ.Z ~ 0 (ex: joelho 90 horizontal).
    Inverte sinal dos vizinhos — conectores do fitting apontam para dentro, nao para fora.
    """
    try:
        owner = target_connector.Owner
        if hasattr(owner, 'ConnectorManager'):
            cm = owner.ConnectorManager
        elif hasattr(owner, 'MEPModel') and owner.MEPModel:
            cm = owner.MEPModel.ConnectorManager
        else:
            return default
        neighbor_slopes = []
        for conn in cm.Connectors:
            if not conn.IsConnected:
                continue
            bz = conn.CoordinateSystem.BasisZ
            dxy_n = sqrt(bz.X ** 2 + bz.Y ** 2)
            if dxy_n < 0.0001:
                continue
            s = bz.Z / dxy_n
            if abs(s) > 0.0005:
                neighbor_slopes.append(s)
        if not neighbor_slopes:
            return default
        return -(sum(neighbor_slopes) / len(neighbor_slopes))
    except Exception:
        return default


def apply_slope_from_connector(moved_pipe, target_connector):
    """
    Aplica slope ao tubo movido baseado no BasisZ do conector alvo.
    Ajusta o Z do endpoint livre via LocationCurve.

    IMPORTANTE: deve ser chamado dentro de Transaction ativa, apos connect_elements()
                ou connect_elements_no_rotate().
    So aplicavel quando o elemento movido e um Pipe nao-vertical.

    Args:
        moved_pipe (Pipe): Tubo que foi movido e conectado
        target_connector (Connector): Conector do elemento alvo

    Returns:
        bool: True se slope foi aplicado, False se operacao foi ignorada (SKIP)
    """
    loc = moved_pipe.Location
    if not isinstance(loc, LocationCurve):
        return False

    # Derivar slope do BasisZ do conector alvo
    bz = target_connector.CoordinateSystem.BasisZ
    dxy = sqrt(bz.X ** 2 + bz.Y ** 2)
    if dxy < 0.0001:  # alvo vertical - sem slope de referencia
        return False
    slope = bz.Z / dxy

    # Joelho 90° horizontal: BasisZ.Z = 0, slope = 0 → buscar nos vizinhos do fitting
    if abs(slope) < 0.0005:
        slope = _derive_slope_from_neighbors(target_connector, slope)

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)

    # Identificar endpoint fixo (conectado) e endpoint livre
    # tol = 0.002 ft (~0.6 mm): preciso o suficiente apos Location.Move()
    tol = 0.002
    p0_dist = p0.DistanceTo(target_connector.Origin)
    p1_dist = p1.DistanceTo(target_connector.Origin)
    p0_is_fixed = p0_dist < tol and p0_dist <= p1_dist
    fixed_pt = p0 if p0_is_fixed else p1
    free_pt  = p1 if p0_is_fixed else p0

    # Calcular nova posicao Z do endpoint livre
    h_dist = sqrt((free_pt.X - fixed_pt.X) ** 2 + (free_pt.Y - fixed_pt.Y) ** 2)
    if h_dist < 0.001:  # pipe muito curto ou conector centrado
        return False

    new_z    = fixed_pt.Z + slope * h_dist
    new_free = XYZ(free_pt.X, free_pt.Y, new_z)
    new_p0   = fixed_pt if p0_is_fixed else new_free
    new_p1   = new_free  if p0_is_fixed else fixed_pt

    if new_p0.DistanceTo(new_p1) < 0.001:
        return False

    try:
        loc.Curve = Line.CreateBound(new_p0, new_p1)
        return True
    except Exception:
        return False


def validate_connectors_compatible(conn1, conn2, allow_connected=False):
    """
    Valida se dois conectores são compatíveis para conexão.

    Args:
        conn1 (Connector): Primeiro conector
        conn2 (Connector): Segundo conector
        allow_connected (bool): Se True, permite conectores já conectados (serão desconectados)

    Returns:
        tuple: (bool, str) - (é_compatível, mensagem_erro)

    Example:
        >>> valid, msg = validate_connectors_compatible(conn1, conn2)
        >>> if not valid:
        ...     print(msg)
    """
    # Verificar domínio
    if conn1.Domain != conn2.Domain:
        return False, "Dominios incompativeis: {} vs {}".format(
            conn1.Domain, conn2.Domain
        )

    # Verificar forma do conector (round/rectangular)
    try:
        if conn1.Shape != conn2.Shape:
            return False, "Formas incompativeis: {} vs {}".format(
                conn1.Shape, conn2.Shape
            )
    except Exception:
        pass

    # Verificar tamanho
    try:
        if str(conn1.Shape) == "Round":
            r1, r2 = conn1.Radius, conn2.Radius
            if abs(r1 - r2) > 0.00164:  # ~0.5 mm em feet
                d1 = int(round(r1 * 2 * 304.8))
                d2 = int(round(r2 * 2 * 304.8))
                return False, "Diametros incompativeis: {}mm vs {}mm".format(d1, d2)
        else:
            if (abs(conn1.Width - conn2.Width) > 0.001 or
                    abs(conn1.Height - conn2.Height) > 0.001):
                return False, "Dimensoes incompativeis: {}x{} vs {}x{}".format(
                    int(round(conn1.Width * 304.8)),
                    int(round(conn1.Height * 304.8)),
                    int(round(conn2.Width * 304.8)),
                    int(round(conn2.Height * 304.8))
                )
    except Exception:
        pass  # conectores sem propriedade de tamanho (ex: eletrica)

    # Verificar se já conectados (se não permitido)
    if not allow_connected:
        if conn1.IsConnected:
            return False, "Primeiro conector ja esta conectado"

        if conn2.IsConnected:
            return False, "Segundo conector ja esta conectado"

    return True, ""
