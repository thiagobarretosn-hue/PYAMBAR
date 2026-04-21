# -*- coding: utf-8 -*-
"""
Nome: _inherit_pipe_params.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
Herda parametros de texto de Pipes para Fittings/Accessories conectados.
Suporta chain traversal (fitting->fitting->...->pipe).
Filtra apenas parametros de texto, excluindo geometria/localizacao/descricao.

Uso em scripts standalone (InheritPipeParams) e integrado nos SnapMEP tools.

Autor: Thiago Barreto Sobral Nunes
Versao: 1.0

Funcoes:
- find_source_pipe(element): Percorre cadeia de conectores ate encontrar pipe
- get_copyable_text_params(source, target): Retorna nomes de params texto copiaveis
- inherit_params_from_pipe(element, doc): Encontra pipe e copia params texto
- inherit_params_batch(elements, doc): Versao batch para multiplos elementos
"""

import os
import sys
import codecs
import json
import hashlib

from Autodesk.Revit.DB import (
    BuiltInCategory, ElementId, ConnectorType, StorageType
)

from Snippets._mep_connector_utils import get_all_connectors


# ============================================================================
# CONSTANTES
# ============================================================================

def _get_id_val(elem_id):
    return elem_id.Value if hasattr(elem_id, 'Value') else elem_id.IntegerValue


# Categorias de pipe
_PIPE_BICS = [
    BuiltInCategory.OST_PipeCurves,
    BuiltInCategory.OST_DuctCurves,
    BuiltInCategory.OST_FlexPipeCurves,
    BuiltInCategory.OST_FlexDuctCurves,
]

# Categorias de fitting/accessory (elementos que RECEBEM params)
_FITTING_BICS = [
    BuiltInCategory.OST_PipeFitting,
    BuiltInCategory.OST_PipeAccessory,
    BuiltInCategory.OST_DuctFitting,
    BuiltInCategory.OST_DuctAccessory,
]

# Parametros excluidos (geometria, localizacao, descricao)
EXCLUDED_PARAMS = {
    # Descricao / identidade de tipo
    "Description",
    "Item Description",
    "Assembly Description",
    "Type Comments",
    "Keynote",
    "Model",
    "Manufacturer",
    "URL",
    # Localizacao / geometria
    "Offset",
    "Start Offset",
    "End Offset",
    "Reference Level",
    "Level",
    "Slope",
    "Length",
    "Size",
    "Diameter",
    "Width",
    "Height",
    "Radius",
    "Angle",
    "Overall Size",
    "Nominal Diameter",
    "Inside Diameter",
    "Outside Diameter",
    # Sistema MEP
    "System Name",
    "System Type",
    "System Classification",
    "System Abbreviation",
    "Service Type",
    "Pipe Segment",
    "Routing Preference",
    "Connection Type",
    # Revit internos
    "Family",
    "Family and Type",
    "Type",
    "Type Name",
    "Category",
    "Image",
    "Comments",
    "Mark",
}

# Cache de category IDs (inicializado lazy)
_pipe_cat_vals = None
_fitting_cat_vals = None


def _init_cat_cache():
    global _pipe_cat_vals, _fitting_cat_vals
    if _pipe_cat_vals is None:
        _pipe_cat_vals = set(
            _get_id_val(ElementId(bic)) for bic in _PIPE_BICS
        )
    if _fitting_cat_vals is None:
        _fitting_cat_vals = set(
            _get_id_val(ElementId(bic)) for bic in _FITTING_BICS
        )


def _is_pipe(element):
    """Verifica se elemento e um pipe/duct."""
    _init_cat_cache()
    cat = element.Category
    if cat:
        return _get_id_val(cat.Id) in _pipe_cat_vals
    return False


def _is_fitting(element):
    """Verifica se elemento e um fitting/accessory."""
    _init_cat_cache()
    cat = element.Category
    if cat:
        return _get_id_val(cat.Id) in _fitting_cat_vals
    return False


# ============================================================================
# CHAIN TRAVERSAL
# ============================================================================

def _pipe_has_params(pipe, param_names):
    """Verifica se o pipe tem pelo menos um param_name com valor preenchido."""
    for name in param_names:
        try:
            p = pipe.LookupParameter(name)
            if p and p.StorageType == StorageType.String:
                val = p.AsString()
                if val and val.strip():
                    return True
        except Exception:
            continue
    return False


def find_source_pipe(element, param_names=None):
    """Percorre cadeia de conectores ate encontrar um pipe com params preenchidos.

    Se param_names fornecido: atravessa pipes sem params e continua BFS
    buscando o pipe que realmente tem os params configurados.
    Se param_names None: retorna o primeiro pipe encontrado (comportamento legado).

    Suporta: fitting->fitting->pipe, pipe->fitting->pipe, etc.

    Args:
        element: Elemento de partida (fitting, accessory ou pipe)
        param_names: Lista de nomes de params para detectar o pipe fonte

    Returns:
        Element or None: Pipe fonte encontrado ou None
    """
    _init_cat_cache()
    visited = set()
    visited.add(_get_id_val(element.Id))
    queue = [element]
    fallback_pipe = None  # primeiro pipe encontrado, caso nenhum tenha params

    while queue:
        current = queue.pop(0)
        try:
            for conn in get_all_connectors(current):
                if conn.ConnectorType != ConnectorType.End:
                    continue
                if not conn.IsConnected:
                    continue
                for ref_conn in conn.AllRefs:
                    if ref_conn.ConnectorType != ConnectorType.End:
                        continue
                    owner = ref_conn.Owner
                    owner_val = _get_id_val(owner.Id)
                    if owner_val in visited:
                        continue
                    visited.add(owner_val)

                    if _is_pipe(owner):
                        if param_names is None:
                            return owner  # comportamento legado: primeiro pipe
                        if _pipe_has_params(owner, param_names):
                            return owner  # pipe com params: fonte encontrada
                        if fallback_pipe is None:
                            fallback_pipe = owner
                        # pipe sem params: continuar BFS atraves dele
                        queue.append(owner)
                    elif _is_fitting(owner):
                        queue.append(owner)
        except Exception:
            continue

    return fallback_pipe


def find_connected_fittings(pipe):
    """Encontra todos os fittings/accessories diretamente conectados a um pipe.

    Args:
        pipe: Elemento pipe/duct

    Returns:
        list: Fittings/accessories conectados
    """
    _init_cat_cache()
    fittings = []
    try:
        for conn in get_all_connectors(pipe):
            if conn.ConnectorType != ConnectorType.End:
                continue
            if not conn.IsConnected:
                continue
            for ref_conn in conn.AllRefs:
                if ref_conn.ConnectorType != ConnectorType.End:
                    continue
                owner = ref_conn.Owner
                if _is_fitting(owner):
                    owner_val = _get_id_val(owner.Id)
                    if not any(_get_id_val(f.Id) == owner_val for f in fittings):
                        fittings.append(owner)
    except Exception:
        pass
    return fittings


# ============================================================================
# PARAMETROS TEXTO
# ============================================================================

def get_copyable_text_params(source, target, excluded=None):
    """Retorna lista de nomes de parametros texto copiaveis.

    Filtra:
    - Apenas StorageType.String
    - Nao read-only no destino
    - Nao esta na blacklist EXCLUDED_PARAMS
    - Existe em ambos source e target

    Args:
        source: Elemento origem (pipe)
        target: Elemento destino (fitting/accessory)
        excluded: Set adicional de nomes a excluir (opcional)

    Returns:
        list: Nomes de parametros copiaveis
    """
    if excluded is None:
        excluded = EXCLUDED_PARAMS
    else:
        excluded = EXCLUDED_PARAMS | set(excluded)

    # Coletar params texto do source com valor
    source_text = set()
    for param in source.Parameters:
        if param.StorageType != StorageType.String:
            continue
        val = param.AsString()
        if val is not None and val.strip() != "":
            name = param.Definition.Name
            if name not in excluded:
                source_text.add(name)

    if not source_text:
        return []

    # Filtrar: existe no target e e editavel
    copyable = []
    for param in target.Parameters:
        if param.IsReadOnly:
            continue
        if param.StorageType != StorageType.String:
            continue
        name = param.Definition.Name
        if name in source_text and name not in excluded:
            copyable.append(name)

    return sorted(copyable)


def _copy_text_params(source, target, param_names):
    """Copia parametros texto de source para target.

    DEVE ser chamado DENTRO de uma Transaction.

    Args:
        source: Elemento origem
        target: Elemento destino
        param_names: Lista de nomes de parametros

    Returns:
        int: Quantidade de parametros copiados com sucesso
    """
    copied = 0
    for name in param_names:
        try:
            src_param = source.LookupParameter(name)
            if not src_param or src_param.StorageType != StorageType.String:
                continue
            val = src_param.AsString()
            if val is None:
                continue

            tgt_param = target.LookupParameter(name)
            if not tgt_param or tgt_param.IsReadOnly:
                continue
            if tgt_param.StorageType != StorageType.String:
                continue

            tgt_param.Set(val)
            copied += 1
        except Exception:
            continue
    return copied


# ============================================================================
# FUNCOES PRINCIPAIS
# ============================================================================

def inherit_params_from_pipe(element, param_names=None):
    """Encontra pipe conectado e copia params texto para o elemento.

    DEVE ser chamado DENTRO de uma Transaction.

    Args:
        element: Fitting/accessory destino
        param_names: Lista de nomes de parametros (opcional).
                     Se None, detecta automaticamente todos os params texto copiaveis.

    Returns:
        dict: {'pipe_id': int or None, 'copied': int, 'params': list}
    """
    result = {'pipe_id': None, 'copied': 0, 'params': []}

    if not _is_fitting(element):
        return result

    pipe = find_source_pipe(element, param_names=param_names)
    if not pipe:
        return result

    result['pipe_id'] = _get_id_val(pipe.Id)

    if param_names is None:
        param_names = get_copyable_text_params(pipe, element)

    if not param_names:
        return result

    result['params'] = param_names
    result['copied'] = _copy_text_params(pipe, element, param_names)
    return result


def inherit_params_batch(elements, param_names=None):
    """Versao batch: copia params do pipe conectado para multiplos elementos.

    Aceita fittings/accessories E pipes como destino.
    Para pipes: faz BFS atraves de fittings ate encontrar outro pipe fonte.

    DEVE ser chamado DENTRO de uma Transaction.

    Args:
        elements: Lista de fittings/accessories/pipes
        param_names: Lista de nomes (opcional). Se None, auto-detecta.

    Returns:
        dict: {'total': int, 'copied': int, 'skipped': int}
    """
    stats = {'total': len(elements), 'copied': 0, 'skipped': 0}

    # Cache pipe -> param_names para evitar recalculo
    pipe_params_cache = {}

    for element in elements:
        if not _is_fitting(element) and not _is_pipe(element):
            stats['skipped'] += 1
            continue

        # param_names passado para find_source_pipe para atravessar pipes sem params
        pipe = find_source_pipe(element, param_names=param_names if param_names else None)
        if not pipe:
            stats['skipped'] += 1
            continue

        pipe_val = _get_id_val(pipe.Id)

        # Determinar param_names
        if param_names:
            names_to_copy = param_names
        else:
            if pipe_val not in pipe_params_cache:
                pipe_params_cache[pipe_val] = get_copyable_text_params(pipe, element)
            names_to_copy = pipe_params_cache[pipe_val]

        if not names_to_copy:
            stats['skipped'] += 1
            continue

        count = _copy_text_params(pipe, element, names_to_copy)
        stats['copied'] += count

    return stats
