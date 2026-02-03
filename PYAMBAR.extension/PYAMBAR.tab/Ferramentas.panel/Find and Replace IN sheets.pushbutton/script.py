# -*- coding: utf-8 -*-
"""
Ferramenta para Localizar e Substituir dados em Tabelas (Schedules).
COMPATIBILIDADE REVIT 2026: Correcao de ElementId.Value (64-bit).

Versao: 5.6 (Fix IronPython 3 - unicode/codecs)
Autor: Thiago Barreto (Refactored by pyRevit Expert)
Diretrizes: v3.0

CORRECOES v5.6:
- Fix: unicode -> str (IronPython 3)
- Fix: open() -> codecs.open() para encoding
"""

__title__ = "Localizar e\nSubstituir (Tabelas)"
__author__ = "Thiago Barreto"
__version__ = "5.6"
__doc__ = "Substitui valores em colunas especificas de tabelas do Revit."

import os
import re
import traceback
import json
import codecs
from datetime import datetime

import System
from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    LabelUtils,
    StorageType,
    Transaction,
    ViewSchedule,
)
from pyrevit import forms, revit, script
from System.Collections.ObjectModel import ObservableCollection

# --- CONFIGURAÇÕES GLOBAIS ---
logger = script.get_logger()
doc = revit.doc
output = script.get_output()

# Diretório de logs
LOG_DIR = os.path.join(os.path.expanduser("~"), ".pyrevit_find_replace_logs")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except:
        LOG_DIR = None

# --- UTILITÁRIOS ---

def safe_str(obj):
    """Converte objeto para string UTF-8 segura."""
    try:
        if obj is None:
            return ""
        return str(obj)
    except:
        return "<erro str>"

def get_id_value(element_id):
    """Retorna valor do ElementId (compatível 2024+)."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue

class ScheduleWrapper(object):
    def __init__(self, view_schedule):
        self.Element = view_schedule
        self.Name = view_schedule.Name
        self.Id = view_schedule.Id

class ColumnWrapper(object):
    def __init__(self, field, display_name, field_name):
        self.Field = field
        self.Name = display_name
        self.FieldName = field_name  # Nome real para LookupParameter

def perform_replace(original_text, find_str, replace_str, match_case, use_regex=False):
    """
    Lógica de substituição com suporte a regex.

    Args:
        original_text: Texto original
        find_str: Texto/padrão a buscar
        replace_str: Texto de substituição
        match_case: Diferenciar maiúsculas/minúsculas
        use_regex: Usar expressões regulares

    Returns:
        tuple: (novo_texto, foi_alterado)
    """
    if not original_text:
        return original_text, False

    # Garantir strings
    original_text = str(original_text) if original_text else ""
    find_str = str(find_str) if find_str else ""
    replace_str = str(replace_str) if replace_str is not None else ""

    try:
        if use_regex:
            # Modo REGEX
            flags = 0 if match_case else re.IGNORECASE
            new_text = re.sub(find_str, replace_str, original_text, flags=flags)
            return new_text, (new_text != original_text)
        else:
            # Modo NORMAL
            if match_case:
                if find_str in original_text:
                    return original_text.replace(find_str, replace_str), True
            else:
                if find_str.lower() in original_text.lower():
                    pattern = re.compile(re.escape(find_str), re.IGNORECASE)
                    new_text = pattern.sub(replace_str, original_text)
                    if new_text != original_text:
                        return new_text, True
    except Exception as e:
        # Em caso de erro de regex, retornar original
        logger.warning("Erro na substituição: {}".format(e))
        return original_text, False

    return original_text, False

# --- LÓGICA DE NEGÓCIO ---

def get_parameter_name_from_id(param_id):
    """Recupera nome do parâmetro dado ElementId."""
    if param_id == ElementId.InvalidElementId:
        return None

    try:
        raw_val = get_id_value(param_id)
        int_id = int(raw_val)

        if int_id > 0:
            try:
                elem = doc.GetElement(param_id)
                if elem: return elem.Name
            except: pass

        try:
            bip_enum = System.Enum.ToObject(BuiltInParameter, int_id)
            if bip_enum is not None:
                return LabelUtils.GetLabelFor(bip_enum)
        except: pass
    except: pass

    return None

def get_all_schedules():
    """Retorna todas as tabelas editáveis."""
    schedules = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()
    valid = []
    for s in schedules:
        if s.IsTitleblockRevisionSchedule or s.IsInternalKeynoteSchedule or s.IsTemplate:
            continue
        valid.append(ScheduleWrapper(s))

    valid.sort(key=lambda x: x.Name)
    return valid

def is_field_editable(view_schedule, field):
    """
    Verifica se um campo pode ser editado nos elementos.
    Testa até 20 elementos ou até encontrar um editável (mais preciso).
    """
    try:
        elements = FilteredElementCollector(doc, view_schedule.Id).ToElements()
        field_name = field.GetName()

        # Converter para lista uma vez apenas (performance)
        elem_list = list(elements)
        total = len(elem_list)

        # Testar até 20 elementos OU todos se houver menos
        test_limit = min(20, total)

        for i in range(test_limit):
            elem = elem_list[i]
            param = elem.LookupParameter(field_name)
            if param and not param.IsReadOnly and param.StorageType == StorageType.String:
                return True

        return False
    except:
        return False

def get_schedule_columns(view_schedule):
    """Retorna APENAS colunas editáveis."""
    definition = view_schedule.Definition
    field_order = definition.GetFieldOrder()

    columns = []
    for index, field_id in enumerate(field_order):
        field = definition.GetField(field_id)
        if field.IsHidden:
            continue

        # Filtrar apenas campos editáveis
        if not is_field_editable(view_schedule, field):
            continue

        display_name = field.ColumnHeading
        field_name = field.GetName()

        if not display_name:
            display_name = field_name if field_name else "Coluna {}".format(index + 1)

        final_string = display_name
        if field_name and display_name and field_name != display_name:
            final_string = "{} ({})".format(display_name, field_name)

        columns.append(ColumnWrapper(field, final_string, field_name))

    return columns

def preview_replacements(schedule_wrapper, column_wrapper, find_str, replace_str, match_case, use_regex):
    """
    Faz preview das substituições SEM aplicar.

    Returns:
        dict: {
            'total_elements': int,
            'affected_count': int,
            'examples': [(old_value, new_value), ...]
        }
    """
    view_schedule = schedule_wrapper.Element
    field_name = column_wrapper.FieldName

    elements = FilteredElementCollector(doc, view_schedule.Id).ToElements()
    elem_list = list(elements)
    total = len(elem_list)

    affected = 0
    examples = []

    for el in elem_list:
        try:
            param = el.LookupParameter(field_name)

            if param and not param.IsReadOnly and param.StorageType == StorageType.String:
                curr = param.AsString() or ""
                new_val, changed = perform_replace(curr, find_str, replace_str, match_case, use_regex)

                if changed:
                    affected += 1
                    # Guardar até 5 exemplos
                    if len(examples) < 5:
                        examples.append((curr, new_val))
        except:
            pass

    return {
        'total_elements': total,
        'affected_count': affected,
        'examples': examples
    }

def execute_replacement(schedule_wrapper, column_wrapper, find_str, replace_str, match_case, use_regex):
    """Executa a substituição usando LookupParameter."""
    view_schedule = schedule_wrapper.Element
    field_name = column_wrapper.FieldName  # Nome real do campo

    elements = FilteredElementCollector(doc, view_schedule.Id).ToElements()
    count = 0
    errors = 0

    t = Transaction(doc, "PYAMBAR: Replace Tabela")
    t.Start()

    with forms.ProgressBar(title="Processando...", step=1, cancellable=True) as pb:
        elem_list = list(elements)
        total = len(elem_list)

        for i, el in enumerate(elem_list):
            if pb.cancelled:
                break
            pb.update_progress(i, total)

            try:
                # ✅ FIX: Usar LookupParameter (compatível com todos os tipos)
                param = el.LookupParameter(field_name)

                if param and not param.IsReadOnly and param.StorageType == StorageType.String:
                    curr = param.AsString() or ""
                    new_val, changed = perform_replace(curr, find_str, replace_str, match_case, use_regex)
                    if changed:
                        param.Set(new_val)
                        count += 1
            except Exception:
                errors += 1
                # Descomentar para debug: print("Erro ID {}: {}".format(get_id_value(el.Id), e))

    t.Commit()
    return count, errors

def save_operation_log(log_data):
    """Salva log da operacao em JSON."""
    if not LOG_DIR:
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, "find_replace_{}.json".format(timestamp))

        with codecs.open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        output.print_md("**Log salvo:** `{}`".format(log_file))
        logger.info("Log salvo em: {}".format(log_file))
    except Exception as e:
        logger.warning("Nao foi possivel salvar log: {}".format(e))

# --- INTERFACE WPF ---

class FindReplaceScheduleWindow(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.WPFWindow.__init__(self, xaml_file)

        self.schedule_wrappers = get_all_schedules()
        self.column_wrappers = []

        sched_names = ObservableCollection[System.String]()
        for s in self.schedule_wrappers:
            sched_names.Add(s.Name)

        self.cb_schedules.ItemsSource = sched_names
        self.cb_schedules.SelectionChanged += self.on_schedule_changed

        self.select_active_view_if_schedule()
        self.load_config()

    def select_active_view_if_schedule(self):
        active = doc.ActiveView
        if isinstance(active, ViewSchedule):
            for i, s in enumerate(self.schedule_wrappers):
                if s.Id == active.Id:
                    self.cb_schedules.SelectedIndex = i
                    break

    def on_schedule_changed(self, sender, args):
        """Ao mudar a tabela, atualiza APENAS colunas editáveis."""
        idx = self.cb_schedules.SelectedIndex

        if idx >= 0:
            wrapper = self.schedule_wrappers[idx]
            try:
                # Mostrar "Carregando..." enquanto filtra
                self.lbl_info.Text = "Analisando colunas editáveis..."
                self.cb_columns.IsEnabled = False

                self.column_wrappers = get_schedule_columns(wrapper.Element)

                col_names = ObservableCollection[System.String]()
                for c in self.column_wrappers:
                    name = c.Name if c.Name else "<???>"
                    col_names.Add(name)

                self.cb_columns.ItemsSource = col_names
                self.cb_columns.IsEnabled = True

                if col_names.Count > 0:
                    self.cb_columns.SelectedIndex = 0
                    self.lbl_info.Text = "{} coluna(s) editável(is).".format(col_names.Count)
                else:
                    self.lbl_info.Text = "Nenhuma coluna editável nesta tabela."

            except Exception as e:
                msg = "Erro ao carregar colunas: {}".format(e)
                print(msg)
                self.lbl_info.Text = msg

    def load_config(self):
        cfg = script.get_config()
        self.tb_find.Text = getattr(cfg, "last_find", "")
        self.tb_replace.Text = getattr(cfg, "last_replace", "")
        self.cb_match_case.IsChecked = getattr(cfg, "match_case", False)
        self.cb_use_regex.IsChecked = getattr(cfg, "use_regex", False)

    def save_config(self):
        cfg = script.get_config()
        cfg.last_find = self.tb_find.Text
        cfg.last_replace = self.tb_replace.Text
        cfg.match_case = self.cb_match_case.IsChecked
        cfg.use_regex = self.cb_use_regex.IsChecked
        script.save_config()

    def preview_click(self, sender, args):
        """Mostra preview das mudanças sem aplicar."""
        s_idx = self.cb_schedules.SelectedIndex
        c_idx = self.cb_columns.SelectedIndex

        if s_idx < 0 or c_idx < 0:
            forms.alert("Selecione Tabela e Coluna.")
            return
        if not self.tb_find.Text:
            forms.alert("Digite o texto para buscar.")
            return

        sched = self.schedule_wrappers[s_idx]
        col = self.column_wrappers[c_idx]
        find = self.tb_find.Text
        repl = self.tb_replace.Text
        match = self.cb_match_case.IsChecked
        regex = self.cb_use_regex.IsChecked

        # Fazer preview
        try:
            preview = preview_replacements(sched, col, find, repl, match, regex)

            msg = "PREVIEW DE ALTERAÇÕES\n\n"
            msg += "Tabela: {}\n".format(safe_str(sched.Name))
            msg += "Coluna: {}\n".format(safe_str(col.Name))
            msg += "\nTotal de elementos: {}\n".format(preview['total_elements'])
            msg += "Serão alterados: {}\n".format(preview['affected_count'])

            if preview['examples']:
                msg += "\nExemplos (até 5):\n"
                for i, (old, new) in enumerate(preview['examples'], 1):
                    msg += "\n{}. ANTES: {}\n   DEPOIS: {}".format(i, old, new)

            forms.alert(msg, title="Preview")
        except Exception as e:
            forms.alert("Erro ao gerar preview:\n\n{}".format(str(e)))

    def replace_click(self, sender, args):
        s_idx = self.cb_schedules.SelectedIndex
        c_idx = self.cb_columns.SelectedIndex

        if s_idx < 0 or c_idx < 0:
            forms.alert("Selecione Tabela e Coluna.")
            return
        if not self.tb_find.Text:
            forms.alert("Digite o texto.")
            return

        self.save_config()
        self.DialogResult = True
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()

def main():
    try:
        xaml_path = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        if not os.path.exists(xaml_path):
            forms.alert("UI não encontrada.")
            return

        window = FindReplaceScheduleWindow(xaml_path)

        if window.show_dialog():
            s_idx = window.cb_schedules.SelectedIndex
            c_idx = window.cb_columns.SelectedIndex

            sched = window.schedule_wrappers[s_idx]
            col = window.column_wrappers[c_idx]

            find = window.tb_find.Text
            repl = window.tb_replace.Text
            match = window.cb_match_case.IsChecked
            regex = window.cb_use_regex.IsChecked

            output.print_md("---")
            output.print_md("## Find and Replace v5.5")
            output.print_md("**Tabela:** {}".format(safe_str(sched.Name)))
            output.print_md("**Coluna:** {}".format(safe_str(col.Name)))
            output.print_md("**Buscar:** `{}`".format(find))
            output.print_md("**Substituir:** `{}`".format(repl))
            output.print_md("**Match Case:** {}".format("Sim" if match else "Não"))
            output.print_md("**Regex:** {}".format("Sim" if regex else "Não"))
            output.print_md("---\n")

            cnt, err = execute_replacement(sched, col, find, repl, match, regex)

            # Salvar log
            log_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "document": doc.Title,
                "schedule": safe_str(sched.Name),
                "column": safe_str(col.Name),
                "find_text": find,
                "replace_text": repl,
                "match_case": match,
                "use_regex": regex,
                "success_count": cnt,
                "error_count": err
            }
            save_operation_log(log_data)

            # Resultado
            output.print_md("✅ **Concluído:** {} substituições".format(cnt))
            if err > 0:
                output.print_md("⚠️ **Erros/Ignorados:** {}".format(err))

            msg = "Substituições realizadas: {}".format(cnt)
            if err > 0:
                msg += "\nErros/Ignorados: {}".format(err)
            forms.alert(msg, title="Concluído")

    except Exception:
        logger.error(traceback.format_exc())
        output.print_md("\n❌ **ERRO:**\n```\n{}\n```".format(traceback.format_exc()))

if __name__ == '__main__':
    main()
