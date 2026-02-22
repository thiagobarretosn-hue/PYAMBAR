# -*- coding: utf-8 -*-
"""
ParamForge v1.0
Ferramenta unificada de analise visual e documentacao por parametros.
Combina funcionalidades de Color-FiLL Forge + SchedulePlumbing.
"""
__title__ = "Param\nForge"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"

import os
import sys
import traceback

import clr
clr.AddReference("System")
clr.AddReference("System.Core")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

# Adicionar pasta do script ao path para imports locais
SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Adicionar lib/ ao path para Snippets
LIB_PATH = os.path.join(SCRIPT_DIR, '..', '..', '..', '..', 'lib')
LIB_PATH = os.path.normpath(LIB_PATH)
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, HOST_APP

# Transaction wrapper (funciona dentro de ShowDialog)
try:
    from Snippets import _transaction
    ef_Transaction = _transaction.ef_Transaction
except ImportError:
    import contextlib
    @contextlib.contextmanager
    def ef_Transaction(doc, name):
        t = Transaction(doc, name)
        t.Start()
        try:
            yield
            t.Commit()
        except Exception:
            t.RollBack()
            raise

doc = revit.doc
uidoc = revit.uidoc
rvt_year = int(HOST_APP.app.VersionNumber)


def main():
    from pf_window import ParamForgeWindow

    selected_elements = []

    while True:
        w = ParamForgeWindow(doc, uidoc, rvt_year, ef_Transaction)
        if selected_elements:
            w.set_selection(selected_elements)
        w.ShowDialog()

        if w.resultado == "__RESELECT__":
            try:
                refs = uidoc.Selection.PickObjects(
                    ObjectType.Element, "Selecione elementos para analise")
                selected_elements = [doc.GetElement(r.ElementId) for r in refs]
                if not selected_elements:
                    break
            except OperationCanceledException:
                # Usuario cancelou a selecao - reabrir sem selecao
                selected_elements = []
                continue
            except Exception:
                break
        else:
            break


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(str(e))
        traceback.print_exc()
