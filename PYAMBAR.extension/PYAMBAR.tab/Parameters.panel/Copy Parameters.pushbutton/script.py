# -*- coding: utf-8 -*-
__title__ = "Copy Parameters"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "6.0"
__doc__ = """
Copy Parameters v6.0 - Unified Workflow

✨ WORKFLOW SIMPLIFICADO:
1. Execute o script
2. Clique para selecionar elemento FONTE
3. Clique para selecionar elemento(s) DESTINO
4. Parâmetros do config.json são copiados automaticamente

🔧 Refatorado com snippets reutilizáveis
📦 Integrado com Config Parameters
⚡ Workflow único: sempre interativo + config automático

_____________________________________________________________________
COMO USAR:
1. Configure parâmetros usando "Config Parameters" (opcional)
2. Execute "Copy Parameters"
3. Selecione elemento FONTE
4. Selecione elemento(s) DESTINO
5. Parâmetros são copiados automaticamente

💡 Se config.json não existir, você pode selecionar parâmetros manualmente

_____________________________________________________________________
Última atualização: [01.12.2025] - v6.0 - Workflow Unificado
"""

# ============================================================================
# IMPORTS
# ============================================================================

# Standard library
import clr
import os
import json
import sys

# Add lib path for Snippets
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

# Revit API
from Autodesk.Revit.DB import (
    Transaction, BuiltInParameter, StorageType, ElementId
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

# pyRevit
from pyrevit import forms, script, revit

# Snippets
from Snippets.validation._preconditions import validate_all_preconditions
from Snippets.parameters._parameter_operations import batch_copy_parameters

# Globals
doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def load_config_from_project():
    """
    Carrega configuração de parâmetros da pasta DAT do projeto.

    Hierarquia:
    1. DAT/pyambar_params_{hash}.json (config do projeto)
    2. config.json na raiz do script (fallback/padrão)

    Returns:
        list: Lista de parâmetros configurados ou lista vazia
    """
    import codecs
    import hashlib

    # 1. Tentar carregar da pasta DAT do projeto
    try:
        project_path = doc.PathName
        if project_path:
            project_dir = os.path.dirname(project_path)
            dat_folder = os.path.join(project_dir, "DAT")

            # Hash do projeto
            project_hash = hashlib.md5(project_path.encode('utf-8')).hexdigest()[:8]
            config_filename = "pyambar_params_{}.json".format(project_hash)
            config_path = os.path.join(dat_folder, config_filename)

            # Se existir, carregar
            if os.path.exists(config_path):
                with codecs.open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    parameters = config_data.get('parameters', [])
                    if parameters:
                        return parameters
    except:
        pass

    # 2. Fallback: config.json na raiz (padrão corporativo)
    try:
        config_path = os.path.join(PATH_SCRIPT, 'config.json')
        if os.path.exists(config_path):
            with codecs.open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                parameters = config.get('parameters_to_copy', [])
                if parameters:
                    return parameters
    except Exception as e:
        forms.alert("Erro ao ler config: {}".format(str(e)))

    return []


def get_parameters_from_element(element):
    """
    Extrai parâmetros do elemento (do Copy Parameters v2.0).
    Retorna lista de nomes de parâmetros modificáveis.

    Args:
        element: Elemento do Revit

    Returns:
        list: Lista de nomes de parâmetros modificáveis
    """
    params = []
    for param in element.Parameters:
        # Pular read-only e built-in críticos
        if param.IsReadOnly:
            continue

        # Pular parâmetros críticos do sistema
        try:
            builtin = param.Definition.BuiltInParameter
            if builtin in [
                BuiltInParameter.ELEM_CATEGORY_PARAM,
                BuiltInParameter.ELEM_FAMILY_PARAM,
                BuiltInParameter.ELEM_TYPE_PARAM,
                BuiltInParameter.ELEM_CATEGORY_PARAM_MT
            ]:
                continue
        except:
            pass

        param_name = param.Definition.Name
        if param_name and param_name not in params:
            params.append(param_name)

    return sorted(params)


def select_parameters_dialog(available_parameters):
    """
    Dialog para selecionar parâmetros (do Copy Parameters v2.0).

    Args:
        available_parameters (list): Lista de parâmetros disponíveis

    Returns:
        list: Parâmetros selecionados ou lista vazia se cancelado
    """
    selected = forms.SelectFromList.show(
        available_parameters,
        title="Selecionar Parâmetros para Copiar",
        button_name="Copiar Parâmetros",
        multiselect=True,
        width=500,
        height=600
    )
    return selected if selected else []


# ============================================================================
# WORKFLOW UNIFICADO
# ============================================================================

def unified_copy_workflow():
    """
    Workflow unificado v6.0:
    1. Seleção interativa de fonte e destinos
    2. Uso automático de config.json (se existir)
    3. Fallback para dialog manual se config vazio
    """
    # 1) Selecionar elemento fonte
    try:
        with forms.WarningBar(title='Selecione o elemento FONTE'):
            ref_source = uidoc.Selection.PickObject(
                ObjectType.Element,
                "Selecione o elemento FONTE dos parâmetros"
            )
            source_element = doc.GetElement(ref_source.ElementId)
    except OperationCanceledException:
        return
    except Exception as e:
        forms.alert("Erro ao selecionar fonte:\n\n{}".format(str(e)))
        return

    # 2) Selecionar elementos destino
    try:
        with forms.WarningBar(title='Selecione os elementos DESTINO (Finish quando concluir)'):
            refs_targets = uidoc.Selection.PickObjects(
                ObjectType.Element,
                "Selecione os elementos DESTINO (vários)"
            )
            target_elements = [doc.GetElement(r.ElementId) for r in refs_targets]
    except OperationCanceledException:
        return
    except Exception as e:
        forms.alert("Erro ao selecionar destinos:\n\n{}".format(str(e)))
        return

    if not target_elements:
        forms.alert("Nenhum elemento destino selecionado")
        return

    # 3) Carregar parâmetros da pasta DAT do projeto
    selected_params = load_config_from_project()

    # Se config vazio, usar dialog manual
    if not selected_params:
        available_params = get_parameters_from_element(source_element)
        if not available_params:
            forms.alert("Nenhum parâmetro modificável encontrado no elemento fonte")
            return

        # Dialog para selecionar parâmetros
        selected_params = select_parameters_dialog(available_params)
        if not selected_params:
            return

    # 4) Copiar usando snippet
    success_count = 0
    fail_count = 0

    with forms.ProgressBar(title="Copiando parâmetros ({} elementos)".format(len(target_elements)),
                           cancellable=True) as pb:
        with Transaction(doc, "Copy Parameters") as t:
            t.Start()

            try:
                results = batch_copy_parameters(
                    source_element=source_element,
                    target_elements=target_elements,
                    param_names=selected_params
                )

                success_count = results['success_count']
                fail_count = results['failed_count']

                t.Commit()

            except Exception as e:
                t.RollBack()
                forms.alert("Erro na transação:\n\n{}".format(str(e)))
                return

    # 5) Completamente silencioso - sem alerts
    # Operação concluída sem interrupções


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Validação
    validation_result = validate_all_preconditions(
        doc=doc,
        uidoc=uidoc,
        min_selection=None,  # Não exigir pré-seleção
        check_worksets=True
    )

    if not validation_result:
        sys.exit()

    # Executar workflow unificado
    try:
        unified_copy_workflow()

    except OperationCanceledException:
        pass  # Usuário cancelou, não fazer nada

    except Exception as e:
        forms.alert("ERRO:\n\n{}".format(str(e)))
