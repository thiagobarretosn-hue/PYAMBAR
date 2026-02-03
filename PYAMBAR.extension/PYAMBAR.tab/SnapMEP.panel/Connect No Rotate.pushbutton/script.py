# -*- coding: utf-8 -*-
"""
Connect No Rotate v2.2
Conecta elementos MEP sem herdar inclinacao do alvo

Autor: Thiago Barreto Sobral Nunes
Versao: 2.2
Data: 2026-01-19

DESCRICAO:
Move e conecta elementos MEP SEM ROTACIONAR.
Move o elemento ate o alvo, conectando sem alterar orientacao.
Mantem a orientacao original do elemento movido.

WORKFLOW:
1. Execute o script
2. Selecione o elemento ALVO (fixo)
3. Selecione o elemento a ser MOVIDO
4. O elemento movido se conecta ao alvo sem rotacionar
"""

__title__ = "Conectar\nSem Rotação"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "2.2"
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
    get_connector_manager,
    get_connector_closest_to,
    connect_elements_no_rotate,
    validate_connectors_compatible,
    MEPElementFilter
)

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Funcao principal de execucao do script."""
    try:
        # PASSO 1: Selecionar elemento ALVO (fixo)
        with forms.WarningBar(title="PASSO 1/2: Elemento ALVO"):
            ref1 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione elemento ALVO (fixo)"
            )

        target_element = doc.GetElement(ref1)
        target_point = ref1.GlobalPoint

        # PASSO 2: Selecionar elemento a MOVER
        with forms.WarningBar(title="PASSO 2/2: Elemento a MOVER"):
            ref2 = uidoc.Selection.PickObject(
                ObjectType.Element,
                MEPElementFilter(),
                "Selecione elemento a MOVER"
            )

        moved_element = doc.GetElement(ref2)
        moved_point = ref2.GlobalPoint

        # Validar nao e mesmo elemento
        if target_element.Id == moved_element.Id:
            forms.alert(
                "Voce selecionou o mesmo elemento duas vezes!\n\n"
                "Selecione elementos diferentes:\n"
                "- Primeiro: elemento ALVO (fixo)\n"
                "- Segundo: elemento a MOVER",
                title="Erro de Selecao",
                warn_icon=True,
                exitscript=True
            )

        # Obter conectores (apenas unused)
        cm_moved = get_connector_manager(moved_element)
        cm_target = get_connector_manager(target_element)

        moved_connector = get_connector_closest_to(cm_moved.UnusedConnectors, moved_point)
        target_connector = get_connector_closest_to(cm_target.UnusedConnectors, target_point)

        if not moved_connector or not target_connector:
            forms.alert(
                "Nao ha conectores disponiveis.\n\n"
                "Verifique se:\n"
                "- Conectores nao estao ja conectados\n"
                "- Elementos possuem conectores livres",
                title="Sem Conectores",
                warn_icon=True,
                exitscript=True
            )

        # Validar compatibilidade
        is_valid, error_msg = validate_connectors_compatible(
            moved_connector,
            target_connector,
            allow_connected=False
        )

        if not is_valid:
            forms.alert(
                "Conectores incompativeis!\n\n{}".format(error_msg),
                title="Erro de Validacao",
                warn_icon=True,
                exitscript=True
            )

        # Conectar usando snippet (SEM rotacao)
        with revit.Transaction("Conectar Sem Rotacao"):
            success = connect_elements_no_rotate(
                moved_element,
                moved_connector,
                target_connector,
                auto_disconnect=True
            )

            if not success:
                forms.alert(
                    "Falha ao conectar elementos.\n\n"
                    "Verifique se os elementos podem ser movidos.",
                    title="Erro",
                    warn_icon=True
                )

    except OperationCanceledException:
        pass  # Usuario cancelou - silencioso

    except AttributeError:
        forms.alert(
            "Elemento sem conectores MEP.\n\n"
            "Selecione tubos, dutos, conexoes ou equipamentos MEP.",
            title="Erro de Validacao",
            warn_icon=True
        )

    except Exception as e:
        import traceback
        print("\n" + "="*60)
        print("ERRO - Connect No Rotate v2.2")
        print("="*60)
        print(traceback.format_exc())
        print("="*60 + "\n")

        forms.alert(
            "Erro ao conectar elementos:\n\n{}".format(e),
            title="Erro",
            warn_icon=True
        )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
