# -*- coding: utf-8 -*-
"""
Disconnect v7.1
Desconecta elementos MEP e separa sistemas automaticamente

Autor: Thiago Barreto Sobral Nunes
Versao: 7.1
Data: 2026-01-19

DESCRICAO:
Desconecta elementos MEP e forca regeneracao para separar sistemas.
Identifica automaticamente a conexao entre dois elementos e a remove.

WORKFLOW:
1. Execute o script
2. Selecione o PRIMEIRO elemento MEP conectado
3. Selecione o SEGUNDO elemento MEP conectado
4. Elementos sao desconectados e sistemas separados
"""

__title__ = "Desconectar"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "7.1"
__persistentengine__ = True

# ============================================================================
# IMPORTS
# ============================================================================

import os
import sys

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms

# Snippets locais
from Snippets._mep_connector_utils import (
    get_all_connectors,
    MEPElementFilter
)

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc

# ============================================================================
# HELPERS
# ============================================================================

def find_connection_between_elements(element1, element2):
    """
    Encontra a conexao entre dois elementos MEP.

    Returns:
        tuple: (connector1, connector2) se conectados, (None, None) caso contrario
    """
    try:
        connectors1 = get_all_connectors(element1)

        for conn1 in connectors1:
            if not conn1.IsConnected:
                continue

            for ref_conn in conn1.AllRefs:
                if ref_conn.Owner.Id == element2.Id:
                    return conn1, ref_conn

        return None, None

    except Exception:
        return None, None


def disconnect_elements(conn1, conn2):
    """
    Desconecta dois conectores e regenera o documento.

    Args:
        conn1: Primeiro conector
        conn2: Segundo conector

    Returns:
        bool: True se sucesso
    """
    conn1.DisconnectFrom(conn2)
    doc.Regenerate()
    return True


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Funcao principal de execucao do script."""
    try:
        # PASSO 1: Selecionar primeiro elemento
        with forms.WarningBar(title="PASSO 1/2: Selecione PRIMEIRO elemento MEP"):
            ref1 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione o PRIMEIRO elemento MEP conectado"
            )

        element1 = doc.GetElement(ref1)

        # PASSO 2: Selecionar segundo elemento
        with forms.WarningBar(title="PASSO 2/2: Selecione SEGUNDO elemento MEP"):
            ref2 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione o SEGUNDO elemento MEP conectado"
            )

        element2 = doc.GetElement(ref2)

        # Validar nao e mesmo elemento
        if element1.Id == element2.Id:
            forms.alert(
                "Voce selecionou o mesmo elemento duas vezes!\n\n"
                "Selecione dois elementos DIFERENTES que estao conectados.",
                title="Erro de Selecao",
                warn_icon=True,
                exitscript=True
            )

        # Encontrar conexao
        conn1, conn2 = find_connection_between_elements(element1, element2)

        if not conn1 or not conn2:
            forms.alert(
                "Elementos nao estao conectados entre si.\n\n"
                "Verifique se:\n"
                "- Existe uma conexao direta entre eles\n"
                "- Os conectores estao visiveis na vista",
                title="Sem Conexao",
                warn_icon=True,
                exitscript=True
            )

        # Desconectar
        with revit.Transaction("Desconectar MEP"):
            disconnect_elements(conn1, conn2)

    except OperationCanceledException:
        pass  # Usuario cancelou - silencioso

    except Exception as e:
        import traceback
        print("\n" + "="*60)
        print("ERRO - Disconnect v7.1")
        print("="*60)
        print(traceback.format_exc())
        print("="*60 + "\n")

        forms.alert(
            "Erro ao desconectar elementos:\n\n{}".format(e),
            title="Erro",
            warn_icon=True
        )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
