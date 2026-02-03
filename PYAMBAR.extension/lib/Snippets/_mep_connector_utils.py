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

from math import pi
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
    try:
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
        
    except Exception:
        return False


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

    # Verificar se já conectados (se não permitido)
    if not allow_connected:
        if conn1.IsConnected:
            return False, "Primeiro conector ja esta conectado"

        if conn2.IsConnected:
            return False, "Segundo conector ja esta conectado"

    return True, ""
