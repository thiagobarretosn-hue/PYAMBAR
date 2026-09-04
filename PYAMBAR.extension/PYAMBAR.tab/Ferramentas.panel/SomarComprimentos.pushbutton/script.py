# -*- coding: utf-8 -*-
"""
Somar Comprimentos v3.4
Soma comprimentos de tubulações (e conexões com comprimento real) e registra
em parâmetro compartilhado.

Autor: Thiago Barreto Sobral Nunes
Versão: 3.4
Data: 2026-07-21

CHANGELOG:
v3.4 - Comprimento sempre editado/exibido em polegadas fracionarias (ex.
       "42 1/2\""), independente da unidade configurada no projeto Revit.
       Aceita digitar tanto fracionario ("42 1/2") quanto decimal ("42.5")
       — o parser do Revit reconhece os dois formatos automaticamente mesmo
       com a Units fixa em fracionario.
v3.3 - Soma tambem o comprimento de fittings (Conexoes de tubo / Conexoes do
       conduite) que tenham o parametro compartilhado "Comprimento" — usado
       pelas pecas Uponor AquaPEX que simulam curvas na mangueira PEX flexivel
       (a mangueira e uma peca so, mas as curvas sao modeladas em outra
       categoria e antes eram ignoradas na soma).
       Abre picker de selecao quando nada esta selecionado no Revit.
       Log movido para %APPDATA%\\pyRevit\\PYAMBAR\\SomarComprimentos\\ (padrao
       do projeto — antes gravava em ~/.pyrevit_sum_lengths_logs).
       Corrigido try/except: o "except OperationCanceledException" externo
       nunca era alcancado (o except Exception interno capturava tudo antes).
v3.2 - (sem changelog registrado)
v3.1 - Padronizacao: usar revit.doc/uidoc em vez de __revit__

DESCRIÇÃO:
Soma comprimentos de tubulações selecionadas (mais o comprimento de eventuais
conexões que representem curvas reais, ex. AquaPEX), permite edição manual do
valor e registra automaticamente em todas as tubulações no parâmetro
"Segment Total Length". Detecta e usa automaticamente as unidades de
comprimento configuradas no projeto.

WORKFLOW:
1. Selecione as tubulações (e conexões, se houver) desejadas — ou deixe sem
   seleção para escolher na hora
2. Execute o script
3. Verifique o comprimento total calculado
4. Edite o valor se necessário (nas unidades do projeto)
5. Confirme para registrar em todas as tubulações selecionadas

REQUISITOS:
- Parâmetro compartilhado "Segment Total Length" deve existir
- Parâmetro deve estar vinculado à categoria Pipes
- Parâmetro não pode ser somente leitura
"""

__title__ = "Somar\nComprimentos"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.4"

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

import sys
import os
import json
import codecs
import traceback
from datetime import datetime

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from System import Guid

from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
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

# Parametro compartilhado "Comprimento" — usado por familias de fitting (ex.
# Bend-Uponor-AquaPEX Long) para guardar o comprimento real de curvas
# simuladas. Vinculado as categorias Conexoes de tubo / Conexoes do conduite.
FITTING_LENGTH_PARAM_GUID = "2de0de19-9e8f-487e-80f3-ab4fc0c10a7d"

# Simbolo de polegada (") usado no FormatOptions fixo de exibicao/edicao
INCH_SYMBOL_ID = "autodesk.unit.symbol:inchDoubleQuote-1.0.1"

# Precisao de exibicao/edicao do comprimento em polegadas fracionarias.
# Ajustavel conforme tolerancia de corte de campo (1/16" = padrao comum).
FRACTIONAL_INCH_ACCURACY = 1.0 / 16.0

# Categorias de fitting cujo comprimento entra na soma (via parametro acima)
FITTING_CATEGORY_IDS = set(
    get_element_id_value(ElementId(bic)) for bic in (
        BuiltInCategory.OST_PipeFitting,
        BuiltInCategory.OST_ConduitFitting,
    )
)

# Diretório de logs (padrão APPDATA do projeto)
_APPDATA_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'SomarComprimentos')
LOG_DIR = os.path.join(_APPDATA_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except Exception:
        LOG_DIR = None

# ============================================================================
# FUNÇÕES AUXILIARES - LOGGING
# ============================================================================

def save_operation_log(operation_data):
    """
    Salva log da operação em arquivo JSON.

    Note:
        Salva em %APPDATA%\\pyRevit\\PYAMBAR\\SomarComprimentos\\logs\\
        Formato: sum_YYYYMMDD_HHMMSS.json
    """
    if not LOG_DIR:
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, "sum_{}.json".format(timestamp))

        # codecs.open (não open() nativo) — IronPython grava em cp1252 sem isso
        # e o JSON quebra ao ser lido como UTF-8 (padrão validado no ModelLogger)
        with codecs.open(log_file, 'w', encoding='utf-8') as f:
            json.dump(operation_data, f, indent=2, ensure_ascii=False)

        output.print_md("📄 **Log salvo:** {}".format(log_file))
    except Exception as e:
        output.print_md("⚠️ Aviso: Não foi possível salvar log: {}".format(str(e)))

# ============================================================================
# FUNÇÕES AUXILIARES - UNIDADES
# ============================================================================

def get_display_units():
    """
    Cria uma Units independente do documento, fixa em polegadas fracionárias
    (ex: 42 1/2"). Usada para editar/exibir o comprimento total sempre em
    polegadas, ignorando a configuração de unidades do projeto Revit.

    Note:
        UnitFormatUtils.TryParse aceita tanto fracionário ("42 1/2\"") quanto
        decimal ("42.5\"" ou "42.5" sem símbolo) mesmo com essas Units fixas
        em fracionário — o parser do Revit reconhece os dois formatos
        automaticamente (validado via MCP em modelo real).
    """
    format_options = FormatOptions(UnitTypeId.FractionalInches)
    format_options.Accuracy = FRACTIONAL_INCH_ACCURACY
    format_options.SetSymbolTypeId(ForgeTypeId(INCH_SYMBOL_ID))

    display_units = Units(UnitSystem.Imperial)
    display_units.SetFormatOptions(SpecTypeId.Length, format_options)
    return display_units


def format_length(value_internal, display_units):
    """
    Formata comprimento de unidades internas (pés) para string em polegadas
    fracionárias (ex: '42 1/2"').
    """
    try:
        formatted = UnitFormatUtils.Format(
            display_units,
            SpecTypeId.Length,
            value_internal,
            False
        )
        return formatted.strip()
    except Exception as e:
        output.print_md("Aviso ao formatar comprimento: {}".format(str(e)))
        inches = UnitUtils.ConvertFromInternalUnits(value_internal, UnitTypeId.Inches)
        return '{:.3f}"'.format(inches)


def parse_length(value_str, display_units):
    """
    Converte string em polegadas (decimal ou fracionário) para valor interno (pés).

    Returns:
        tuple: (is_valid: bool, result: float_or_error_msg)
    """
    try:
        success_tuple = UnitFormatUtils.TryParse(
            display_units,
            SpecTypeId.Length,
            value_str
        )

        if success_tuple[0]:
            value_internal = success_tuple[1]
            if value_internal < 0:
                return False, "Valor nao pode ser negativo"
            return True, value_internal
        else:
            return False, "Formato invalido (use polegadas: ex. 42.5 ou 42 1/2)"

    except Exception:
        try:
            cleaned = value_str.strip().replace(',', '.').replace('"', '')
            value_in = float(cleaned)
            if value_in < 0:
                return False, "Valor nao pode ser negativo"
            value_internal = UnitUtils.ConvertToInternalUnits(value_in, UnitTypeId.Inches)
            return True, value_internal
        except ValueError:
            return False, "Valor invalido: '{}'".format(value_str)

# ============================================================================
# FUNÇÕES AUXILIARES - SELEÇÃO
# ============================================================================

class _PipeOrFittingFilter(ISelectionFilter):
    """Permite selecionar apenas Pipe, Pipe Fitting e Conduit Fitting."""

    def AllowElement(self, element):
        if isinstance(element, Pipe):
            return True
        category = element.Category
        if category and get_element_id_value(category.Id) in FITTING_CATEGORY_IDS:
            return True
        return False

    def AllowReference(self, reference, position):
        return True


def pick_pipes_and_fittings():
    """
    Abre picker de seleção para tubulações e conexões (quando nada
    esta selecionado no Revit).

    Returns:
        list: Elementos escolhidos (pode ser vazio se o usuário cancelar)
    """
    try:
        with forms.WarningBar(title='Selecione as tubulações/conexões e clique em "Finish"'):
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                _PipeOrFittingFilter(),
                "Selecione tubulações e conexões"
            )
        return [doc.GetElement(ref) for ref in refs]
    except OperationCanceledException:
        return []


def classify_selection(elements):
    """
    Separa elementos selecionados em tubos, fittings com comprimento e ignorados.

    Returns:
        tuple: (pipes: list, fittings: list, ignored_count: int)
    """
    pipes = []
    fittings = []
    ignored_count = 0

    for element in elements:
        if isinstance(element, Pipe):
            pipes.append(element)
            continue

        category = element.Category
        if category and get_element_id_value(category.Id) in FITTING_CATEGORY_IDS:
            fittings.append(element)
            continue

        ignored_count += 1

    return pipes, fittings, ignored_count

# ============================================================================
# FUNÇÕES AUXILIARES - COMPRIMENTOS
# ============================================================================

def get_pipe_length(pipe):
    """
    Obtém comprimento do tubo em unidades internas (pés).

    Note:
        Usa o parâmetro built-in CURVE_ELEM_LENGTH
    """
    length_param = pipe.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
    if length_param:
        return length_param.AsDouble()
    return 0.0


def get_fitting_length(fitting):
    """
    Obtém o comprimento real de uma conexão (fitting) em unidades internas (pés),
    via o parâmetro compartilhado "Comprimento" (GUID FITTING_LENGTH_PARAM_GUID).

    Note:
        Fittings genéricos (cotovelo/luva padrão) não têm esse parâmetro
        preenchido e contribuem 0 — só peças como o AquaPEX Bend (que
        simulam a curva da mangueira PEX) têm valor real aqui.
    """
    try:
        param = fitting.get_Parameter(Guid(FITTING_LENGTH_PARAM_GUID))
        if param and param.HasValue:
            return param.AsDouble()
    except Exception:
        pass
    return 0.0

# ============================================================================
# FUNÇÕES AUXILIARES - PARÂMETROS
# ============================================================================

def validate_parameter(element, param_name):
    """
    Valida se parâmetro existe e pode ser modificado.

    Returns:
        tuple: (is_valid: bool, result: Parameter_or_error_msg)
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

    Note:
        Apenas tubulações recebem o parâmetro — fittings entram no cálculo
        do total, mas "Segment Total Length" está vinculado só a Pipes.

    Returns:
        tuple: (success_count: int, errors: list)
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
            errors.append({
                'id': pipe.Id,
                'error': result
            })

    return success_count, errors

# ============================================================================
# INTERFACE E EXECUÇÃO
# ============================================================================

def main():
    # PASSO 1: Obter seleção (ou abrir picker se nada selecionado)
    selection_ids = uidoc.Selection.GetElementIds()
    if selection_ids:
        elements = [doc.GetElement(elem_id) for elem_id in selection_ids]
    else:
        elements = pick_pipes_and_fittings()

    if not elements:
        forms.alert(
            "Nenhuma tubulacao/conexao selecionada.\n\n"
            "Selecione pelo menos uma tubulacao e execute novamente.",
            title="Selecao Invalida",
            warn_icon=True
        )
        return

    pipes, fittings, ignored_count = classify_selection(elements)

    if not pipes:
        forms.alert(
            "Nenhuma tubulacao (Pipe) na selecao.\n\n"
            "O parametro 'Segment Total Length' so pode ser registrado em "
            "tubulacoes — selecione ao menos uma.",
            title="Selecao Invalida",
            warn_icon=True
        )
        return

    output.print_md("---")
    output.print_md("# Somar Comprimentos v{}".format(__version__))
    output.print_md("---")
    output.print_md("🔧 **Tubulações selecionadas:** {}".format(len(pipes)))
    if fittings:
        output.print_md("🔩 **Conexões com comprimento:** {}".format(len(fittings)))
    if ignored_count:
        output.print_md("⚠️ **Elementos ignorados (categoria não suportada):** {}".format(ignored_count))

    # PASSO 2: Unidades fixas em polegadas (padrão da ferramenta, independente do projeto)
    display_units = get_display_units()
    output.print_md("📏 **Unidades:** polegadas (padrão fixo da ferramenta)")

    # PASSO 3: Calcular comprimento total (tubos + conexões)
    pipes_length_internal = sum(get_pipe_length(pipe) for pipe in pipes)
    fittings_length_internal = sum(get_fitting_length(fitting) for fitting in fittings)
    total_length_internal = pipes_length_internal + fittings_length_internal
    total_formatted = format_length(total_length_internal, display_units)

    if fittings_length_internal:
        output.print_md("➕ **Tubos:** {} | **Conexões:** {} | **Total:** {}".format(
            format_length(pipes_length_internal, display_units),
            format_length(fittings_length_internal, display_units),
            total_formatted
        ))
    else:
        output.print_md("➕ **Comprimento total calculado:** {}".format(total_formatted))
    output.print_md("---\n")

    # PASSO 4: Solicitar edição do valor
    user_input = forms.ask_for_string(
        default=total_formatted,
        prompt="Comprimento total (polegadas — decimal ou fracionário):",
        title="Somar Comprimentos v{}".format(__version__)
    )

    if not user_input:
        output.print_md("⚠️ **Operação cancelada pelo usuário.**")
        return

    is_valid, result = parse_length(user_input, display_units)

    if not is_valid:
        forms.alert(
            "Valor invalido:\n\n{}".format(result),
            title="Erro de Validacao",
            warn_icon=True
        )
        return

    final_length_internal = result

    # PASSO 5: Atualizar parâmetros em transação
    t = Transaction(doc, 'Registrar Comprimento Total')
    t.Start()

    try:
        success_count, errors = update_pipes_parameter(pipes, final_length_internal)
        t.Commit()
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
        return

    # Preparar dados de log
    # int() explicito: ElementId.Value no Revit 2026 retorna Int64 do .NET,
    # que json.dump nao serializa (TypeError "... is not JSON serializable")
    pipe_ids = [int(get_element_id_value(pipe.Id)) for pipe in pipes]
    fitting_ids = [int(get_element_id_value(fitting.Id)) for fitting in fittings]
    log_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "document": doc.Title,
        "parameter_name": PARAM_NAME,
        "pipe_count": len(pipes),
        "pipe_ids": pipe_ids,
        "fitting_count": len(fittings),
        "fitting_ids": fitting_ids,
        "fitting_length_internal": fittings_length_internal,
        "total_length": final_length_internal,
        "total_length_formatted": format_length(final_length_internal, display_units),
        "success_count": success_count,
        "error_count": len(errors),
        "errors": [{"id": int(get_element_id_value(e['id'])), "error": e['error']} for e in errors]
    }

    # PASSO 6: Relatório de resultado
    output.print_md("\n---")
    output.print_md("## ✅ RESULTADO")
    output.print_md("---")
    output.print_md("**Tubulações atualizadas:** {}/{}".format(success_count, len(pipes)))
    output.print_md("**Valor registrado:** {}".format(
        format_length(final_length_internal, display_units)
    ))

    if errors:
        output.print_md("\n### ⚠️ AVISOS ({} erros):".format(len(errors)))
        for error in errors[:5]:
            output.print_md("- **Tubo ID {}**: {}".format(
                get_element_id_value(error['id']),
                error['error']
            ))
        if len(errors) > 5:
            output.print_md("- ... e mais {} erros".format(len(errors) - 5))

    output.print_md("---\n")

    save_operation_log(log_data)

    if success_count == len(pipes):
        forms.alert(
            "Comprimento total registrado com sucesso!\n\n"
            "Tubulacoes atualizadas: {}\n"
            "Valor: {}".format(
                success_count,
                format_length(final_length_internal, display_units)
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

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except OperationCanceledException:
        pass
    except Exception as e:
        output.print_md("\n---")
        output.print_md("## ❌ ERRO GERAL")
        output.print_md("---")
        output.print_md("```\n{}\n```".format(str(e)))
        output.print_md("\n```python\n{}\n```".format(traceback.format_exc()))
        output.print_md("---\n")

        forms.alert(
            "Erro durante execucao:\n\n{}".format(str(e)),
            title="Erro",
            warn_icon=True
        )
