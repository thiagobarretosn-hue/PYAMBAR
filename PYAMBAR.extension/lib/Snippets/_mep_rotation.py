# -*- coding: utf-8 -*-
"""
D:\RVT 26\scripts\PYAMBAR(lab).extension\lib\Snippets\_mep_rotation.py
Descrição: Rotação de conexões MEP no eixo correto
Uso: from Snippets import _mep_rotation
Última atualização: 24.11.2025
"""

import math
from Autodesk.Revit.DB import Line

def degrees_to_radians(degrees):
    """Converte graus para radianos."""
    return degrees * (math.pi / 180.0)


def get_rotation_axis(element):
    """
    Obtém eixo de rotação prioritizando conector CONECTADO.
    Rotação ocorre no eixo do conector conectado (BasisZ).
    
    Args:
        element: FamilyInstance (conexão MEP)
        
    Returns:
        Line: Eixo de rotação ilimitado ou None
    """
    try:
        mep_model = element.MEPModel
        if not mep_model or not mep_model.ConnectorManager:
            return None
        
        connectors = mep_model.ConnectorManager.Connectors
        if connectors.IsEmpty:
            return None

        # Prioridade: conector CONECTADO
        connected_connector = None
        first_connector = None
        
        for conn in connectors:
            if first_connector is None:
                first_connector = conn
            
            if conn.IsConnected:
                connected_connector = conn
                break
        
        # Usar conector conectado se existir, senão primeiro
        target_connector = connected_connector if connected_connector else first_connector
        
        if not target_connector:
            return None
        
        # Eixo = origem do elemento + direção do conector (BasisZ)
        origin = element.Location.Point
        direction = target_connector.CoordinateSystem.BasisZ
        
        return Line.CreateUnbound(origin, direction)
        
    except:
        return None
