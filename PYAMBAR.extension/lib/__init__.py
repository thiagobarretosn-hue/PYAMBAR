# -*- coding: utf-8 -*-
"""Biblioteca MicrodesktLT para pyRevit."""

__version__ = "2.0.0"
__author__ = "Seu Nome"

# Importar funções principais para acesso direto
from .mep_utils import (
    get_connector_manager,
    get_connector_closest_to,
    find_closest_connector_pair,
    create_appropriate_fitting,
    validate_connector_compatibility
)

__all__ = [
    'get_connector_manager',
    'get_connector_closest_to', 
    'find_closest_connector_pair',
    'create_appropriate_fitting',
    'validate_connector_compatibility'
]