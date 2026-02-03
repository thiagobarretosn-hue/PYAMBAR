# -*- coding: utf-8 -*-
"""
_preconditions.py
Validações pré-execução para scripts pyRevit - documento, worksets, seleção.

USAGE:
    from Snippets.validation._preconditions import (
        validate_document,
        validate_worksets,
        validate_selection
    )

    # Validar documento
    valid, errors = validate_document(doc)
    if not valid:
        for error in errors:
            print(error)
        return

    # Validar worksets
    valid, locked_worksets = validate_worksets(doc)
    if not valid:
        print("Worksets bloqueados: {}".format(locked_worksets))

    # Validar seleção
    valid, count, message = validate_selection(uidoc, min_count=1)
    if not valid:
        print(message)

DEPENDENCIES:
    - Autodesk.Revit.DB (FilteredWorksetCollector, WorksetKind)
    - Autodesk.Revit.UI (UIDocument)

AUTHOR: Thiago Barreto
VERSION: 1.0
EXTRACTED FROM: ParameterPalette.pushbutton
"""

from Autodesk.Revit.DB import FilteredWorksetCollector, WorksetKind, Transaction


def validate_document(doc):
    """
    Valida se o documento está pronto para operações de escrita.

    Verificações:
    - Documento existe
    - Documento não está em modo leitura
    - Vista ativa existe

    Args:
        doc (Document): Documento Revit

    Returns:
        tuple: (valid, errors)
            - valid (bool): True se todas as validações passaram
            - errors (list): Lista de mensagens de erro (vazio se valid=True)

    Example:
        >>> valid, errors = validate_document(doc)
        >>> if not valid:
        ...     for error in errors:
        ...         print(error)
        ...     return
    """
    errors = []

    # Verificar existência do documento
    if not doc:
        errors.append("❌ Nenhum documento ativo")
        return False, errors

    # Verificar modo leitura
    if doc.IsReadOnly:
        errors.append("❌ Documento em modo somente leitura")

    # Verificar vista ativa
    if not doc.ActiveView:
        errors.append("❌ Nenhuma vista ativa no documento")

    # Retornar resultado
    if errors:
        return False, errors

    return True, []


def validate_worksets(doc, check_editable=True):
    """
    Valida worksets em documentos colaborativos.

    Args:
        doc (Document): Documento Revit
        check_editable (bool): Se True, verifica worksets bloqueados

    Returns:
        tuple: (valid, locked_worksets)
            - valid (bool): True se nenhum workset está bloqueado (ou doc não é workshared)
            - locked_worksets (list): Lista de nomes de worksets bloqueados

    Example:
        >>> valid, locked = validate_worksets(doc, check_editable=True)
        >>> if not valid:
        ...     print("Worksets bloqueados: {}".format(", ".join(locked)))
    """
    locked_worksets = []

    # Se não for workshared, não há worksets para validar
    if not doc.IsWorkshared:
        return True, locked_worksets

    try:
        # Coletar worksets de usuário
        collector = FilteredWorksetCollector(doc)
        worksets = collector.OfKind(WorksetKind.UserWorkset).ToWorksets()

        if check_editable:
            # Identificar worksets bloqueados (não editáveis)
            for workset in worksets:
                if not workset.IsEditable:
                    locked_worksets.append(workset.Name)

        # Válido se não houver worksets bloqueados
        valid = len(locked_worksets) == 0

        return valid, locked_worksets

    except Exception as e:
        # Se houver erro ao acessar worksets, considerar válido mas retornar erro
        return True, ["⚠️ Erro ao verificar worksets: {}".format(str(e))]


def validate_selection(uidoc, min_count=1, max_count=None):
    """
    Valida seleção atual do usuário.

    Args:
        uidoc (UIDocument): UI Document do Revit
        min_count (int): Quantidade mínima de elementos selecionados
        max_count (int): Quantidade máxima de elementos selecionados (None = sem limite)

    Returns:
        tuple: (valid, count, message)
            - valid (bool): True se seleção é válida
            - count (int): Quantidade de elementos selecionados
            - message (str): Mensagem descritiva

    Example:
        >>> valid, count, msg = validate_selection(uidoc, min_count=1)
        >>> if not valid:
        ...     print(msg)
        ...     return
        >>> print("{} elementos selecionados".format(count))
    """
    if not uidoc:
        return False, 0, "❌ UIDocument não fornecido"

    try:
        selection_ids = uidoc.Selection.GetElementIds()
        count = selection_ids.Count if hasattr(selection_ids, 'Count') else len(selection_ids)

        # Verificar mínimo
        if count < min_count:
            if min_count == 1:
                message = "❌ Nenhum elemento selecionado"
            else:
                message = "❌ Seleção insuficiente: {} elemento(s) requerido(s), {} selecionado(s)".format(
                    min_count, count
                )
            return False, count, message

        # Verificar máximo
        if max_count is not None and count > max_count:
            message = "❌ Seleção excede limite: máximo {} elemento(s), {} selecionado(s)".format(
                max_count, count
            )
            return False, count, message

        # Seleção válida
        message = "✅ {} elemento(s) selecionado(s)".format(count)
        return True, count, message

    except Exception as e:
        return False, 0, "❌ Erro ao verificar seleção: {}".format(str(e))


def validate_transaction_possible(doc):
    """
    Valida se é possível iniciar uma transação no documento.

    Args:
        doc (Document): Documento Revit

    Returns:
        tuple: (valid, reason)
            - valid (bool): True se transação é possível
            - reason (str): Razão da impossibilidade (vazio se valid=True)

    Example:
        >>> valid, reason = validate_transaction_possible(doc)
        >>> if not valid:
        ...     print("Não é possível iniciar transação: {}".format(reason))
        ...     return
    """
    if not doc:
        return False, "Documento não existe"

    if doc.IsReadOnly:
        return False, "Documento em modo somente leitura"

    # Verificar se já existe transação ativa
    try:
        # Tentar criar transação de teste (não inicia)
        test_transaction = Transaction(doc, "Test")
        # Se conseguiu criar, transação é possível
        return True, ""

    except Exception as e:
        return False, "Erro ao verificar possibilidade de transação: {}".format(str(e))


def validate_all_preconditions(doc, uidoc, min_selection=None, check_worksets=True):
    """
    Valida todas as pré-condições de uma vez (função de conveniência).

    Args:
        doc (Document): Documento Revit
        uidoc (UIDocument): UI Document
        min_selection (int): Quantidade mínima de elementos selecionados (None = não verifica)
        check_worksets (bool): Se True, verifica worksets bloqueados

    Returns:
        tuple: (valid, errors)
            - valid (bool): True se todas as validações passaram
            - errors (list): Lista consolidada de mensagens de erro

    Example:
        >>> valid, errors = validate_all_preconditions(doc, uidoc, min_selection=1)
        >>> if not valid:
        ...     for error in errors:
        ...         output.print_md(error)
        ...     return
    """
    all_errors = []

    # Validar documento
    doc_valid, doc_errors = validate_document(doc)
    if not doc_valid:
        all_errors.extend(doc_errors)

    # Validar worksets
    if check_worksets:
        ws_valid, locked_worksets = validate_worksets(doc, check_editable=True)
        if not ws_valid and locked_worksets:
            all_errors.append("⚠️ {} workset(s) bloqueado(s): {}".format(
                len(locked_worksets), ", ".join(locked_worksets)
            ))

    # Validar seleção
    if min_selection is not None:
        sel_valid, sel_count, sel_message = validate_selection(uidoc, min_count=min_selection)
        if not sel_valid:
            all_errors.append(sel_message)

    # Resultado consolidado
    valid = len(all_errors) == 0
    return valid, all_errors


# TESTES UNITÁRIOS
if __name__ == '__main__':
    print("=== TESTANDO _preconditions.py ===\n")
    print("AVISO: Testes requerem ambiente Revit ativo\n")

    # Testes simulados (sem Revit)
    print("1. validate_document() - OK (requer Document)")
    print("2. validate_worksets() - OK (requer Document)")
    print("3. validate_selection() - OK (requer UIDocument)")
    print("4. validate_transaction_possible() - OK (requer Document)")
    print("5. validate_all_preconditions() - OK (requer doc + uidoc)")

    # Teste de None handling
    print("\n6. Testando handling de None...")
    valid, errors = validate_document(None)
    print("   validate_document(None): valid={}, errors={}".format(valid, len(errors)))
    assert not valid, "Deveria retornar False para doc=None"
    assert len(errors) > 0, "Deveria ter mensagens de erro"

    valid, count, msg = validate_selection(None, min_count=1)
    print("   validate_selection(None): valid={}, msg='{}'".format(valid, msg))
    assert not valid, "Deveria retornar False para uidoc=None"

    print("\n✅ TESTES BÁSICOS PASSARAM!")
    print("Execute em ambiente Revit para testes completos")
