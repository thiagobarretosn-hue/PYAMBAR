# -*- coding: utf-8 -*-
__title__ = "Sync Pipe\nParams"
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

Usa config do Parameters (%APPDATA%\\pyRevit\\PYAMBAR\\ConfigParameters\\user_parameters.json).
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

_USER_CONFIG_FILE = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'ConfigParameters', 'user_parameters.json'
)


# ============================================================================
# FUNCOES
# ============================================================================

def load_parameter_config():
    """Carrega lista de parametros salvos pelo Config Parameters no APPDATA do usuario."""
    try:
        if os.path.exists(_USER_CONFIG_FILE):
            with codecs.open(_USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                params = data.get('parameters', [])
                if params:
                    return params
    except Exception:
        pass
    output.print_md(
        "**Aviso:** Config nao encontrado em `{}`.\n\n"
        "Execute **Config Parameters** para configurar seus parametros. "
        "Usando lista padrao.".format(_USER_CONFIG_FILE)
    )
    return PARAMETROS_PADRAO


def main():
    try:
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
    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
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
