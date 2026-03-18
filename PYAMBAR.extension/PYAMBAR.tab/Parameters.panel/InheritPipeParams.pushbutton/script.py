# -*- coding: utf-8 -*-
__title__ = "Inherit Pipe\nParams"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0"
__doc__ = """
Inherit Pipe Params v3.0

Copia parametros configurados dos Pipes para os Fittings/Accessories conectados.
Suporta chain traversal: fitting->fitting->...->pipe.

WORKFLOW:
1. Selecione Pipes e/ou Fittings/Accessories
2. Execute o script
3. Fittings selecionados herdam do pipe conectado
4. Pipes selecionados propagam params para fittings conectados

Usa config do Parameters (DAT/pyambar_params_{hash}.json).
Se nao existir config, usa PARAMETROS_PADRAO.
"""

# ============================================================================
# IMPORTS
# ============================================================================

import os
import sys
import traceback
import codecs
import json
import hashlib

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

import clr
clr.AddReference("System")

from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script

from Snippets._inherit_pipe_params import (
    inherit_params_batch, _is_fitting, _is_pipe
)
from Snippets.data._state_persistence import load_state

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

# Mesmos defaults do Config Parameters
PARAMETROS_PADRAO = [
    "Módulo Montagem",
    "WBS",
    "WBS Detail",
    "WBS Instance",
    "WBS Detail Instance",
    "Ambiente",
    "Tipologia UH",
    "Stage"
]

# Localizacao antiga (migracao v1.5)
OLD_CONFIG_FILE = os.path.join(
    os.getenv('APPDATA', ''),
    'PYAMBAR',
    'CopyParameters',
    'user_parameters.json'
)


# ============================================================================
# FUNCOES
# ============================================================================

def load_parameter_config():
    """Carrega config de parametros - mesma hierarquia do Config Parameters.

    1. DAT/pyambar_params_{hash}.json (config do projeto)
    2. user_parameters.json (config de usuario via _state_persistence)
    3. Localizacao antiga v1.5 (migracao)
    4. PARAMETROS_PADRAO (hardcoded)
    """
    # 1. Config do projeto (pasta DAT)
    try:
        project_path = doc.PathName
        if project_path:
            project_dir = os.path.dirname(project_path)
            dat_folder = os.path.join(project_dir, "DAT")
            project_hash = hashlib.md5(project_path.encode('utf-8')).hexdigest()[:8]
            config_filename = "pyambar_params_{}.json".format(project_hash)
            config_path = os.path.join(dat_folder, config_filename)
            if os.path.exists(config_path):
                with codecs.open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    parameters = config_data.get('parameters', [])
                    if parameters:
                        return parameters
    except Exception:
        pass

    # 2. Config de usuario (mesmo path do Config Parameters)
    config_params_path = os.path.join(PATH_SCRIPT, '..', 'Config Parameters.pushbutton')
    config_params_path = os.path.normpath(config_params_path)
    state = load_state(
        script_path=config_params_path,
        state_folder_name="config",
        state_file_name="user_parameters.json"
    )
    if state and 'parameters' in state:
        return state['parameters']

    # 3. Migracao v1.5
    if os.path.exists(OLD_CONFIG_FILE):
        try:
            with codecs.open(OLD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                params = old_data.get('parameters', [])
                if params:
                    return params
        except Exception:
            pass

    # 4. Padrao hardcoded
    return PARAMETROS_PADRAO


def main():
    # ===== SELECAO =====
    selection = revit.get_selection()
    if not selection or len(selection) == 0:
        forms.alert("Selecione elementos antes de executar.", warn_icon=True)
        return

    # ===== FILTRAR DESTINOS (pipes e fittings) =====
    targets = [elem for elem in selection if _is_fitting(elem) or _is_pipe(elem)]

    if not targets:
        forms.alert("Nenhum Pipe/Fitting/Accessory na selecao.", warn_icon=True)
        return

    # ===== CARREGAR CONFIG =====
    param_names = load_parameter_config()

    # ===== COPIAR PARAMETROS (com chain traversal) =====
    with revit.Transaction("Inherit Pipe Params"):
        stats = inherit_params_batch(targets, param_names=param_names)

    # ===== RESULTADO (toast - nao bloqueia) =====
    msg = "{} elementos | {} params copiados".format(
        stats['total'] - stats['skipped'], stats['copied']
    )
    if stats['skipped']:
        msg += " | {} sem fonte".format(stats['skipped'])
    forms.toast(msg, title="Inherit Pipe Params", appid="PYAMBAR")


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except OperationCanceledException:
        pass
    except Exception as e:
        output.print_md("**Erro critico:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
