# -*- coding: utf-8 -*-
__title__   = "Ocultar\nParam."
__author__  = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"
__doc__     = """Oculta (permanentemente na vista) todos os elementos do projeto
que compartilham o mesmo valor de parametro do elemento de referencia.

WORKFLOW:
1. Selecione (ou pre-selecione) um elemento de referencia
2. Escolha o parametro + valor para filtrar
3. Escolha o escopo: Vista Ativa ou Todas as Vistas
4. TODOS os elementos do projeto com esse valor sao ocultados
   independente de categoria

Desfazer: Ctrl+Z (Revit Undo)
"""

import os
import sys

PULLDOWN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
if PULLDOWN_DIR not in sys.path:
    sys.path.insert(0, PULLDOWN_DIR)

from _shared import run_action

if __name__ == '__main__':
    run_action("hide")
