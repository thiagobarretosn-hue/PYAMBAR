# -*- coding: utf-8 -*-
"""
Somar Comprimentos v3.1
Soma comprimentos de tubulações e registra em parâmetro compartilhado

Autor: Thiago Barreto Sobral Nunes
Versão: 3.1
Data: 2026-01-19

CHANGELOG:
v3.1 - Padronizacao: usar revit.doc/uidoc em vez de __revit__

DESCRIÇÃO:
Soma comprimentos de tubulações selecionadas, permite edição manual do valor
e registra automaticamente em todas as tubulações no parâmetro "Segment Total Length".
Detecta e usa automaticamente as unidades de comprimento configuradas no projeto.

WORKFLOW:
1. Selecione as tubulações desejadas
2. Execute o script
3. Verifique o comprimento total calculado
4. Edite o valor se necessário (nas unidades do projeto)
5. Confirme para registrar em todas as tubulações selecionadas

FUNCIONALIDADES:
- Detecção automática de unidades do projeto (m, cm, mm, ft, in)
- Cálculo preciso de comprimentos
- Validação de entrada do usuário
- Atualização em lote de parâmetros
- Relatório com emojis visuais e markdown
- Logging automático de operações em JSON
- Compatibilidade universal (Revit 2019-2026+)

APLICAÇÕES:
- Calcular comprimento total de trechos de tubulação
- Registrar comprimentos de segmentos para quantificação
- Documentar comprimentos customizados
- Facilitar cálculos de materiais

REQUISITOS:
- Parâmetro compartilhado "Segment Total Length" deve existir
- Parâmetro deve estar vinculado à categoria Pipes
- Parâmetro não pode ser somente leitura
"""

__title__ = "Somar\nComprimentos"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.2"

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

import sys
import os
import json
from datetime import datetime

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import Pipe
from pyrevit import forms, script, revit

from Snippets.core._revit_version_helpers import get_element_id_value

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

# Constantes
PARAM_NAME = "Segment Total Length"

# Diretório de logs (user folder)
LOG_DIR = os.path.expanduser("~/.pyrevit_sum_lengths_logs")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except:
        LOG_DIR = None

# ============================================================================
# FUNÇÕES AUXILIARES - LOGGING
# ============================================================================

def save_operation_log(operation_data):
    """
    Salva log da operação em arquivo JSON.

    Args:
        operation_data (dict): Dados da operação

    Note:
        Salva em ~/.pyrevit_sum_lengths_logs/ com timestamp
        Formato: sum_YYYYMMDD_HHMMSS.json
    """
    if not LOG_DIR:
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, "sum_{}.json".format(timestamp))

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(operation_data, f, indent=2, ensure_ascii=False)

        output.print_md("📄 **Log salvo:** {}".format(log_file))
    except Exception as e:
        output.print_md("⚠️ Aviso: Não foi possível salvar log: {}".format(str(e)))

# ============================================================================
# FUNÇÕES AUXILIARES - UNIDADES
# ============================================================================

def get_project_length_units():
    """
    Obtém as unidades de comprimento configuradas no projeto.

    Returns:
        tuple: (FormatOptions, unit_symbol_str)

    Note:
        FormatOptions é usado para formatar/parsear valores
        unit_symbol é uma string legível para o usuário (ex: 'm', 'ft', 'cm')
    """
    # Obter unidades do projeto
    units = doc.GetUnits()
    format_options = units.GetFormatOptions(SpecTypeId.Length)

    # Obter ID do tipo de unidade
    unit_type_id = format_options.GetUnitTypeId()

    # Mapear IDs para símbolos legíveis
    unit_symbols = {
        'autodesk.unit.unit:meters-1.0.1': 'm',
        'autodesk.unit.unit:centimeters-1.0.1': 'cm',
        'autodesk.unit.unit:millimeters-1.0.1': 'mm',
        'autodesk.unit.unit:feet-1.0.1': 'ft',
        'autodesk.unit.unit:feetFractionalInches-1.0.1': 'ft-in',
        'autodesk.unit.unit:inches-1.0.1': 'in',
        'autodesk.unit.unit:fractionalInches-1.0.1': 'in'
    }

    unit_id_str = unit_type_id.TypeId if hasattr(unit_type_id, 'TypeId') else str(unit_type_id)
    unit_symbol = unit_symbols.get(unit_id_str, 'ft')

    return format_options, unit_symbol


def format_length(value_internal, format_options):
    """
    Formata comprimento de unidades internas (pés) para string nas unidades do projeto.

    Args:
        value_internal (float): Valor em unidades internas do Revit (pés)
        format_options (FormatOptions): Opções de formatação do projeto

    Returns:
        str: Valor formatado nas unidades do projeto

    Note:
        Usa UnitFormatUtils.Format() do Revit 2021+
    """
    try:
        formatted = UnitFormatUtils.Format(
            doc.GetUnits(),
            SpecTypeId.Length,
            value_internal,
            False  # não incluir símbolo da unidade
        )
        return formatted.strip()
    except Exception as e:
        # Fallback: formatar manualmente com 3 casas decimais
        print("Aviso ao formatar comprimento: {}".format(str(e)))
        return "{:.3f}".format(value_internal)


def parse_length(value_str, format_options):
    """
    Converte string formatada para valor interno (pés).

    Args:
        value_str (str): String com valor nas unidades do projeto
        format_options (FormatOptions): Opções de formatação do projeto

    Returns:
        tuple: (is_valid: bool, result: float_or_error_msg)

    Note:
        Usa UnitFormatUtils.TryParse() do Revit 2021+
        Se falhar, tenta parse manual assumindo número decimal
    """
    try:
        # Tentar parse usando API do Revit
        success_tuple = UnitFormatUtils.TryParse(
            doc.GetUnits(),
            SpecTypeId.Length,
            value_str
        )

        if success_tuple[0]:  # Parse bem-sucedido
            value_internal = success_tuple[1]

            if value_internal < 0:
                return False, "Valor nao pode ser negativo"

            return True, value_internal
        else:
            return False, "Formato invalido para unidades do projeto"

    except Exception as e:
        # Fallback: tentar parse manual
        try:
            cleaned = value_str.strip().replace(',', '.')
            value = float(cleaned)

            if value < 0:
                return False, "Valor nao pode ser negativo"

            return True, value

        except ValueError:
            return False, "Valor invalido: '{}'".format(value_str)

# ============================================================================
# FUNÇÕES AUXILIARES - TUBULAÇÕES
# ============================================================================

def get_selected_pipes():
    """
    Retorna lista de tubulações selecionadas.

    Returns:
        list: Lista de elementos Pipe selecionados

    Note:
        Filtra apenas elementos do tipo Pipe da seleção atual
    """
    selection_ids = uidoc.Selection.GetElementIds()

    if not selection_ids:
        return []

    pipes = []
    for elem_id in selection_ids:
        element = doc.GetElement(elem_id)
        if isinstance(element, Pipe):
            pipes.append(element)

    return pipes


def get_pipe_length(pipe):
    """
    Obtém comprimento do tubo em unidades internas (pés).

    Args:
        pipe (Pipe): Elemento de tubulação

    Returns:
        float: Comprimento em pés (unidade interna do Revit)

    Note:
        Usa o parâmetro built-in CURVE_ELEM_LENGTH
    """
    length_param = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
    if length_param:
        return length_param.AsDouble()
    return 0.0

# ============================================================================
# FUNÇÕES AUXILIARES - PARÂMETROS
# ============================================================================

def validate_parameter(element, param_name):
    """
    Valida se parâmetro existe e pode ser modificado.

    Args:
        element (Element): Elemento do Revit
        param_name (str): Nome do parâmetro

    Returns:
        tuple: (is_valid: bool, result: Parameter_or_error_msg)

    Note:
        Verifica existência do parâmetro e se não é somente leitura
    """
    param = element.LookupParameter(param_name)

    if not param:
        return False, "Parametro '{}' nao encontrado".format(param_name)

    if param.IsReadOnly:
        return False, "Parametro '{}' e somente leitura".format(param_name)

    return True, param


def update_pipes_parameter(pipes, value_internal):
    """
    Atualiza parâmetro em todas as tubulações.

    Args:
        pipes (list): Lista de elementos Pipe
        value_internal (float): Valor em unidades internas (pés)

    Returns:
        tuple: (success_count: int, errors: list)

    Note:
        Retorna contagem de sucessos e lista de erros com IDs
    """
    success_count = 0
    errors = []

    for pipe in pipes:
        is_valid, result = validate_parameter(pipe, PARAM_NAME)

        if is_valid:
            param = result
            try:
                param.Set(value_internal)
                success_count += 1
            except Exception as e:
                errors.append({
                    'id': pipe.Id,
                    'error': "Erro ao setar valor: {}".format(str(e))
                })
        else:
            error_msg = result
            errors.append({
                'id': pipe.Id,
                'error': error_msg
            })

    return success_count, errors

# ============================================================================
# INTERFACE E EXECUÇÃO
# ============================================================================

def main():
    """
    Função principal de execução do script.

    Workflow:
        1. Valida que existem tubulações selecionadas
        2. Obtém unidades do projeto
        3. Calcula comprimento total
        4. Solicita confirmação/edição do usuário
        5. Atualiza parâmetros em transação
        6. Exibe relatório de resultado
    """
    try:
        # PASSO 1: Validar seleção
        pipes = get_selected_pipes()

        if not pipes:
            forms.alert(
                "Nenhuma tubulacao selecionada.\n\n"
                "Selecione pelo menos uma tubulacao e execute novamente.",
                title="Selecao Invalida",
                warn_icon=True
            )
            sys.exit()

        output.print_md("---")
        output.print_md("# Somar Comprimentos v3.0")
        output.print_md("---")
        output.print_md("🔧 **Tubulações selecionadas:** {}".format(len(pipes)))

        # PASSO 2: Obter unidades do projeto
        format_options, unit_symbol = get_project_length_units()
        output.print_md("📏 **Unidades do projeto:** {}".format(unit_symbol))

        # PASSO 3: Calcular comprimento total
        total_length_internal = sum(get_pipe_length(pipe) for pipe in pipes)
        total_formatted = format_length(total_length_internal, format_options)

        output.print_md("➕ **Comprimento total calculado:** {} {}".format(total_formatted, unit_symbol))
        output.print_md("---\n")

        # PASSO 4: Solicitar edição do valor
        user_input = forms.ask_for_string(
            default=total_formatted,
            prompt="Comprimento total (em {}):".format(unit_symbol),
            title="Somar Comprimentos v2.0"
        )

        # Usuário cancelou
        if not user_input:
            output.print_md("⚠️ **Operação cancelada pelo usuário.**")
            sys.exit()

        # Validar e converter entrada
        is_valid, result = parse_length(user_input, format_options)

        if not is_valid:
            error_msg = result
            forms.alert(
                "Valor invalido:\n\n{}".format(error_msg),
                title="Erro de Validacao",
                warn_icon=True
            )
            sys.exit()

        final_length_internal = result

        # PASSO 5: Atualizar parâmetros em transação
        t = Transaction(doc, 'Registrar Comprimento Total')
        t.Start()

        try:
            success_count, errors = update_pipes_parameter(pipes, final_length_internal)

            t.Commit()

            # Preparar dados de log
            pipe_ids = [get_element_id_value(pipe.Id) for pipe in pipes]
            log_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "document": doc.Title,
                "parameter_name": PARAM_NAME,
                "pipe_count": len(pipes),
                "pipe_ids": pipe_ids,
                "total_length": final_length_internal,
                "total_length_formatted": "{} {}".format(
                    format_length(final_length_internal, format_options),
                    unit_symbol
                ),
                "success_count": success_count,
                "error_count": len(errors),
                "errors": [{"id": get_element_id_value(e['id']), "error": e['error']} for e in errors]
            }

            # PASSO 6: Relatório de resultado
            output.print_md("\n---")
            output.print_md("## ✅ RESULTADO")
            output.print_md("---")
            output.print_md("**Tubulações atualizadas:** {}/{}".format(success_count, len(pipes)))
            output.print_md("**Valor registrado:** {} {}".format(
                format_length(final_length_internal, format_options),
                unit_symbol
            ))

            if errors:
                output.print_md("\n### ⚠️ AVISOS ({} erros):".format(len(errors)))
                for error in errors[:5]:  # Mostrar apenas primeiros 5
                    output.print_md("- **Tubo ID {}**: {}".format(
                        get_element_id_value(error['id']),
                        error['error']
                    ))

                if len(errors) > 5:
                    output.print_md("- ... e mais {} erros".format(len(errors) - 5))

            output.print_md("---\n")

            # Salvar log
            save_operation_log(log_data)

            # Mensagem de sucesso
            if success_count == len(pipes):
                forms.alert(
                    "Comprimento total registrado com sucesso!\n\n"
                    "Tubulacoes atualizadas: {}\n"
                    "Valor: {} {}".format(
                        success_count,
                        format_length(final_length_internal, format_options),
                        unit_symbol
                    ),
                    title="Sucesso",
                    warn_icon=False
                )
            else:
                forms.alert(
                    "Operacao concluida com avisos.\n\n"
                    "Tubulacoes atualizadas: {}/{}\n"
                    "Erros: {}\n\n"
                    "Verifique o console para detalhes.".format(
                        success_count,
                        len(pipes),
                        len(errors)
                    ),
                    title="Concluido com Avisos",
                    warn_icon=True
                )

        except Exception as e:
            t.RollBack()
            error_msg = str(e)

            output.print_md("\n---")
            output.print_md("## ❌ ERRO")
            output.print_md("---")
            output.print_md("```\n{}\n```".format(error_msg))
            output.print_md("---\n")

            forms.alert(
                "Erro ao atualizar tubulacoes:\n\n{}".format(error_msg),
                title="Erro",
                warn_icon=True
            )

    except Exception as e:
        output.print_md("\n---")
        output.print_md("## ❌ ERRO GERAL")
        output.print_md("---")
        output.print_md("```\n{}\n```".format(str(e)))

        import traceback
        output.print_md("\n```python\n{}\n```".format(traceback.format_exc()))
        output.print_md("---\n")

        forms.alert(
            "Erro durante execucao:\n\n{}".format(str(e)),
            title="Erro",
            warn_icon=True
        )

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    main()
