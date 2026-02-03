# -*- coding: utf-8 -*-
"""
Paleta de Parametros v4.3.1 - MODELESS + forms.WPFWindow

Baseado no padrao funcional v3.1 com melhorias:
- Topmost controlavel
- Auto-save dropdown (novos valores salvos no CSV)
- Codigo limpo

FEATURES:
- Carregar CSV (DAT ou raiz)
- Adicionar parametros do projeto
- Remover parametros
- Salvar/Carregar templates
- Estado persistente (APPDATA)

CORRECOES v4.3.1:
- Fix: Hide/Show janela antes de dialogs modais (SelectFromList, ask_for_string)
- Fix: Melhor tratamento de erros e feedback no status
"""
__title__ = "Paleta de\nParametros"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.3.1"

# CRITICO: Necessario para MODELESS
__persistentengine__ = True

import clr
import os
import sys
import json
import codecs
import shutil
import time
from datetime import datetime

# Add lib path for Snippets
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

clr.AddReference("System")
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import Thickness, VerticalAlignment, Visibility, FontWeights
from System.Windows.Controls import Label, ComboBox, StackPanel, CheckBox, Orientation
from System.Windows.Markup import XamlReader

from Autodesk.Revit.DB import Transaction, FilteredElementCollector, SharedParameterElement
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent, TaskDialog

from pyrevit import forms, script, revit

# ============================================================================
# GLOBALS
# ============================================================================
doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

# State em APPDATA
APPDATA = os.getenv('APPDATA')
STATE_DIR = os.path.join(APPDATA, 'pyRevit', 'PYAMBAR', 'ParameterPalette')
if not os.path.exists(STATE_DIR):
    try:
        os.makedirs(STATE_DIR)
    except:
        pass
STATE_FILE = os.path.join(STATE_DIR, 'palette_state.json')


# ============================================================================
# CSV HELPERS
# ============================================================================

def ler_csv_utf8(caminho):
    """Le CSV com encoding UTF-8."""
    try:
        with codecs.open(caminho, 'r', encoding='utf-8-sig') as f:
            linhas = []
            for linha in f:
                linha = linha.strip()
                if linha:
                    valores = [v.strip().strip('"').strip("'") for v in linha.split(',')]
                    linhas.append(valores)
        if not linhas:
            return [], []
        return linhas[0], linhas[1:]
    except Exception as e:
        print("Erro ler CSV: {}".format(e))
        return [], []


def escrever_csv_utf8(caminho, headers, rows):
    """Escreve CSV com encoding UTF-8."""
    try:
        with codecs.open(caminho, 'w', encoding='utf-8-sig') as f:
            f.write(u','.join([u'"{}"'.format(h) for h in headers]) + u'\n')
            for row in rows:
                while len(row) < len(headers):
                    row.append(u'')
                f.write(u','.join([u'"{}"'.format(v) for v in row]) + u'\n')
        return True
    except Exception as e:
        print("Erro escrever CSV: {}".format(e))
        return False


# ============================================================================
# DAT FOLDER
# ============================================================================

def get_dat_folder(document):
    """Obtem pasta DAT do projeto."""
    try:
        if document and document.PathName:
            project_folder = os.path.dirname(document.PathName)
            dat_folder = os.path.join(project_folder, 'DAT')
            if not os.path.exists(dat_folder):
                os.makedirs(dat_folder)
            return dat_folder
    except:
        pass
    return None


def get_project_name(document):
    """Obtem nome do projeto."""
    try:
        if document and document.PathName:
            return os.path.splitext(os.path.basename(document.PathName))[0]
    except:
        pass
    return "projeto"


def get_csv_path(document, script_path):
    """Obtem caminho do CSV (DAT ou raiz)."""
    dat = get_dat_folder(document)
    if dat:
        project_name = get_project_name(document)
        dat_csv = os.path.join(dat, "{}_data.csv".format(project_name))
        if os.path.exists(dat_csv):
            return dat_csv, "DAT"

    root_csv = os.path.join(script_path, 'data.csv')
    if os.path.exists(root_csv):
        return root_csv, "raiz"

    return None, None


def create_backup(csv_path, document):
    """Cria backup do CSV."""
    try:
        dat = get_dat_folder(document)
        if not dat:
            return False, "Sem pasta DAT"
        backup_dir = os.path.join(dat, 'backup')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = "data_backup_{}.csv".format(timestamp)
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(csv_path, backup_path)
        return True, backup_path
    except Exception as e:
        return False, str(e)


# ============================================================================
# TEMPLATES
# ============================================================================

def get_templates_path(document, script_path):
    """Obtem caminho do arquivo de templates."""
    dat = get_dat_folder(document)
    if dat:
        return os.path.join(dat, 'templates.csv')
    return os.path.join(script_path, 'templates.csv')


def load_templates(document, script_path):
    """Carrega templates salvos."""
    templates_path = get_templates_path(document, script_path)
    if not os.path.exists(templates_path):
        return []
    try:
        headers, rows = ler_csv_utf8(templates_path)
        templates = []
        for row in rows:
            if row and row[0].strip():
                name = row[0].strip()
                data = {}
                for i, h in enumerate(headers[1:], 1):
                    if i < len(row):
                        data[h] = row[i]
                templates.append({'name': name, 'data': data})
        return templates
    except:
        return []


def save_template(document, script_path, template_name, param_values):
    """Salva um template."""
    try:
        templates_path = get_templates_path(document, script_path)
        if os.path.exists(templates_path):
            headers, rows = ler_csv_utf8(templates_path)
        else:
            headers = ['Template'] + sorted(param_values.keys())
            rows = []

        for p in param_values.keys():
            if p not in headers:
                headers.append(p)

        new_row = [template_name]
        for h in headers[1:]:
            new_row.append(param_values.get(h, ''))

        found = False
        for i, row in enumerate(rows):
            if row and row[0] == template_name:
                rows[i] = new_row
                found = True
                break
        if not found:
            rows.append(new_row)

        escrever_csv_utf8(templates_path, headers, rows)
        return True
    except:
        return False


# ============================================================================
# STATE MANAGER
# ============================================================================

def save_state(param_controls, current_csv, selected_template=""):
    """Salva estado dos controles."""
    try:
        state = {
            'parameters': {},
            'csv_file': current_csv,
            'selected_template': selected_template,
            'timestamp': datetime.now().isoformat()
        }
        for param_name, controls in param_controls.items():
            combo = controls["combo"]
            toggle = controls["toggle"]
            state['parameters'][param_name] = {
                'enabled': bool(toggle.IsChecked),
                'selected_value': str(combo.Text) if combo.Text else None
            }
        with codecs.open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except:
        pass


def load_state():
    """Carrega estado salvo."""
    try:
        if os.path.exists(STATE_FILE):
            with codecs.open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return None


# ============================================================================
# EXTERNAL EVENT HANDLER
# ============================================================================

class ApplyParametersHandler(IExternalEventHandler):
    """Handler para aplicar parametros via ExternalEvent."""

    def __init__(self):
        self.param_values = None
        self.selected_ids = None
        self.palette_window = None

    def Execute(self, uiapp):
        start_time = time.time()

        try:
            current_doc = uiapp.ActiveUIDocument.Document

            if not self.selected_ids or len(self.selected_ids) == 0:
                TaskDialog.Show("Aviso", "Nenhum elemento selecionado!")
                return

            if not self.param_values:
                TaskDialog.Show("Aviso", "Nenhum parametro para aplicar!")
                return

            success_count = 0
            error_count = 0
            not_found_params = set()

            with Transaction(current_doc, "Aplicar Parametros") as t:
                t.Start()

                try:
                    for elem_id in self.selected_ids:
                        element = current_doc.GetElement(elem_id)

                        if not element:
                            continue

                        # Cache de parametros do elemento
                        elem_params = {}
                        for param in element.Parameters:
                            try:
                                elem_params[param.Definition.Name] = param
                            except:
                                continue

                        # Aplicar parametros
                        for param_name, param_value in self.param_values.items():
                            if not param_value:
                                continue

                            try:
                                if param_name in elem_params:
                                    param = elem_params[param_name]

                                    if param.IsReadOnly:
                                        continue

                                    param.Set(param_value)
                                    success_count += 1
                                else:
                                    not_found_params.add(param_name)

                            except:
                                error_count += 1

                    t.Commit()

                except Exception as e:
                    t.RollBack()
                    TaskDialog.Show("Erro", "Erro ao aplicar: {}".format(str(e)))
                    return

            elapsed = time.time() - start_time

            # Atualizar status
            if self.palette_window:
                msg = "{} aplicacoes em {:.2f}s".format(success_count, elapsed)
                if not_found_params:
                    msg += " | {} nao encontrados".format(len(not_found_params))
                self.palette_window.status_text.Text = msg

        except Exception as e:
            TaskDialog.Show("Erro", str(e))

    def GetName(self):
        return "ApplyParametersHandler"


# ============================================================================
# PALETA - forms.WPFWindow (PADRAO FUNCIONAL)
# ============================================================================

class ParameterPalette(forms.WPFWindow):
    """Paleta MODELESS usando forms.WPFWindow."""

    def __init__(self, external_event, event_handler):
        xaml_file = os.path.join(PATH_SCRIPT, 'ui.xaml')
        forms.WPFWindow.__init__(self, xaml_file)

        self.Closing += self.on_closing

        self.external_event = external_event
        self.event_handler = event_handler
        self.event_handler.palette_window = self

        self.param_controls = {}
        self.csv_data = {}
        self.current_csv = None
        self.templates = []

        # Carregar templates
        self.load_templates()

        # Carregar CSV
        csv_path, csv_source = get_csv_path(doc, PATH_SCRIPT)
        if csv_path:
            self.current_csv = csv_path
            self.load_csv(csv_path)
            self.status_text.Text = "CSV {} carregado".format(csv_source)
        else:
            dat = get_dat_folder(doc)
            if dat:
                self.current_csv = os.path.join(dat, "{}_data.csv".format(get_project_name(doc)))
                escrever_csv_utf8(self.current_csv, [], [])
                self.status_text.Text = "CSV DAT criado (vazio)"
            else:
                self.status_text.Text = "Projeto nao salvo"

        # Restaurar estado
        saved_state = load_state()
        if saved_state:
            self.restore_state(saved_state)

        # Eventos dos botoes
        self.btn_apply.Click += self.apply_parameters
        self.btn_load_csv.Click += self.load_new_csv
        self.btn_save_csv.Click += self.save_csv_to_dat
        self.btn_add_param.Click += self.add_parameter_from_project
        self.btn_remove_param.Click += self.remove_parameter
        self.btn_save_template.Click += self.on_save_template
        self.combo_template.SelectionChanged += self.on_template_selected

        # Eventos das checkboxes
        self.chk_topmost.Checked += self.on_topmost_changed
        self.chk_topmost.Unchecked += self.on_topmost_changed
        self.chk_select_all.Checked += self.on_select_all_checked
        self.chk_select_all.Unchecked += self.on_select_all_unchecked

        # Mostrar janela MODELESS
        self.Show()

    def on_closing(self, sender, args):
        """Salva estado ao fechar."""
        try:
            selected_template = str(self.combo_template.SelectedItem) if self.combo_template.SelectedItem else ""
            save_state(self.param_controls, self.current_csv, selected_template)

            if self.external_event:
                self.external_event.Dispose()
        except:
            pass

    def on_topmost_changed(self, sender, args):
        """Altera Topmost da janela."""
        try:
            self.Topmost = bool(self.chk_topmost.IsChecked)
        except:
            pass

    def on_select_all_checked(self, sender, args):
        """Marca todos os toggles."""
        for controls in self.param_controls.values():
            controls['toggle'].IsChecked = True
        self.status_text.Text = "Todos marcados"

    def on_select_all_unchecked(self, sender, args):
        """Desmarca todos os toggles."""
        for controls in self.param_controls.values():
            controls['toggle'].IsChecked = False
        self.status_text.Text = "Todos desmarcados"

    def load_templates(self):
        """Carrega templates no dropdown."""
        try:
            self.templates = load_templates(doc, PATH_SCRIPT)
            self.combo_template.Items.Clear()
            self.combo_template.Items.Add("[ Nenhum Template ]")
            for t in self.templates:
                self.combo_template.Items.Add(t['name'])
            self.combo_template.SelectedIndex = 0
        except:
            pass

    def on_template_selected(self, sender, args):
        """Aplica template selecionado."""
        try:
            if self.combo_template.SelectedIndex <= 0:
                return
            name = str(self.combo_template.SelectedItem)
            for t in self.templates:
                if t['name'] == name:
                    for param, value in t['data'].items():
                        if param in self.param_controls:
                            self.param_controls[param]['combo'].Text = value
                    self.status_text.Text = "Template '{}' aplicado".format(name)
                    break
        except:
            pass

    def on_save_template(self, sender, args):
        """Salva template atual."""
        try:
            values = self.get_selected_values()
            if not values:
                self.status_text.Text = "Nenhum parametro ativo para salvar"
                return

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                name = forms.ask_for_string(prompt="Nome do template:", title="Salvar Template")
            finally:
                self.Show()

            if not name:
                self.status_text.Text = "Operacao cancelada"
                return

            if save_template(doc, PATH_SCRIPT, name, values):
                self.load_templates()
                self.status_text.Text = "Template '{}' salvo".format(name)
            else:
                self.status_text.Text = "Erro ao salvar template"

        except Exception as e:
            import traceback
            print("Erro save_template: {}".format(traceback.format_exc()))
            TaskDialog.Show("Erro", str(e))

    def create_toggle_checkbox(self, param_name):
        """Cria checkbox toggle estilo iOS."""
        toggle = CheckBox()
        toggle.IsChecked = True
        toggle.Tag = param_name
        toggle.Style = self.FindResource("iOSToggleStyle")
        toggle.Margin = Thickness(0, 0, 8, 0)
        toggle.VerticalAlignment = VerticalAlignment.Center
        return toggle

    def create_editable_combobox(self, options, param_name):
        """Cria combobox editavel."""
        combo = ComboBox()
        combo.IsEditable = True
        combo.Height = 28
        combo.Margin = Thickness(0, 0, 5, 10)
        combo.Tag = param_name

        for option in options:
            if option and option.strip():
                combo.Items.Add(option.strip())

        combo.LostFocus += self.on_combo_lost_focus

        return combo

    def on_combo_lost_focus(self, sender, args):
        """Salva novo valor no CSV quando usuario digita texto novo."""
        try:
            combo = sender
            param_name = str(combo.Tag)
            new_value = combo.Text.strip() if combo.Text else ""

            if not new_value:
                return

            # Verificar se valor ja existe no combo
            existing_values = [str(combo.Items[i]) for i in range(combo.Items.Count)]
            if new_value in existing_values:
                # Apenas salvar estado
                selected_template = str(self.combo_template.SelectedItem) if self.combo_template.SelectedItem else ""
                save_state(self.param_controls, self.current_csv, selected_template)
                return

            # Adicionar ao combo
            combo.Items.Add(new_value)

            # Adicionar ao csv_data local
            if param_name in self.csv_data:
                self.csv_data[param_name].append(new_value)

            # Salvar no CSV
            if self.current_csv:
                self.add_value_to_csv(param_name, new_value)
                self.status_text.Text = "'{}' adicionado a {}".format(new_value, param_name)
        except:
            pass

    def add_value_to_csv(self, param_name, new_value):
        """Adiciona novo valor ao CSV."""
        try:
            if not self.current_csv or not os.path.exists(self.current_csv):
                return

            headers, rows = ler_csv_utf8(self.current_csv)
            if param_name not in headers:
                return

            param_idx = headers.index(param_name)

            # Encontrar linha vazia ou criar nova
            added = False
            for row in rows:
                while len(row) < len(headers):
                    row.append('')
                if not row[param_idx].strip():
                    row[param_idx] = new_value
                    added = True
                    break

            if not added:
                new_row = [''] * len(headers)
                new_row[param_idx] = new_value
                rows.append(new_row)

            escrever_csv_utf8(self.current_csv, headers, rows)
        except:
            pass

    def load_csv(self, csv_path):
        """Carrega CSV e cria controles."""
        try:
            if not os.path.exists(csv_path):
                TaskDialog.Show("Erro", "CSV nao encontrado: {}".format(csv_path))
                return

            self.param_panel.Children.Clear()
            self.param_controls.clear()
            self.csv_data.clear()

            headers, rows = ler_csv_utf8(csv_path)

            # Processar colunas
            columns = [[] for _ in headers]
            for row in rows:
                for i in range(len(headers)):
                    if i < len(row):
                        value = row[i].strip()
                        if value and value not in columns[i]:
                            columns[i].append(value)

            # Criar controles
            for i, param_name in enumerate(headers):
                param_name = param_name.strip()
                if not param_name:
                    continue

                options = columns[i]
                self.csv_data[param_name] = options

                # Row: toggle + label
                row_panel = StackPanel()
                row_panel.Orientation = Orientation.Horizontal
                row_panel.Margin = Thickness(0, 8, 0, 3)

                toggle = self.create_toggle_checkbox(param_name)
                toggle.Checked += self.on_toggle_changed
                toggle.Unchecked += self.on_toggle_changed
                row_panel.Children.Add(toggle)

                label = Label()
                label.Content = param_name
                label.FontSize = 13
                label.FontWeight = FontWeights.SemiBold
                label.Width = 150
                label.VerticalAlignment = VerticalAlignment.Center
                row_panel.Children.Add(label)

                self.param_panel.Children.Add(row_panel)

                # Row: combo
                combo_panel = StackPanel()
                combo_panel.Orientation = Orientation.Horizontal
                combo_panel.Margin = Thickness(55, 0, 0, 0)

                combo = self.create_editable_combobox(options, param_name)
                combo.SelectionChanged += self.on_selection_changed
                combo_panel.Children.Add(combo)

                self.param_panel.Children.Add(combo_panel)

                self.param_controls[param_name] = {
                    "combo": combo,
                    "toggle": toggle
                }

            self.current_csv = csv_path
            self.status_text.Text = "{} parametros carregados".format(len(self.param_controls))

        except Exception as e:
            TaskDialog.Show("Erro", "Erro ao carregar CSV: {}".format(str(e)))

    def restore_state(self, state):
        """Restaura estado salvo."""
        try:
            if 'parameters' not in state:
                return
            for param_name, ps in state['parameters'].items():
                if param_name in self.param_controls:
                    self.param_controls[param_name]['toggle'].IsChecked = ps.get('enabled', True)
                    val = ps.get('selected_value')
                    if val:
                        self.param_controls[param_name]['combo'].Text = val
            if 'selected_template' in state and state['selected_template']:
                for i in range(self.combo_template.Items.Count):
                    if str(self.combo_template.Items[i]) == state['selected_template']:
                        self.combo_template.SelectedIndex = i
                        break
        except:
            pass

    def on_toggle_changed(self, sender, args):
        """Toggle alterado."""
        param_name = sender.Tag
        is_checked = sender.IsChecked

        if param_name in self.param_controls:
            combo = self.param_controls[param_name]["combo"]
            combo.IsEnabled = is_checked

        selected_template = str(self.combo_template.SelectedItem) if self.combo_template.SelectedItem else ""
        save_state(self.param_controls, self.current_csv, selected_template)

    def on_selection_changed(self, sender, args):
        """Selecao alterada no combo."""
        selected_template = str(self.combo_template.SelectedItem) if self.combo_template.SelectedItem else ""
        save_state(self.param_controls, self.current_csv, selected_template)

    def get_selected_values(self):
        """Obtem valores dos parametros ativos."""
        values = {}
        for param_name, controls in self.param_controls.items():
            if controls['toggle'].IsChecked and controls['combo'].Text:
                values[param_name] = controls['combo'].Text.strip()
        return values

    def apply_parameters(self, sender, args):
        """Dispara ExternalEvent para aplicar."""
        try:
            selection = uidoc.Selection
            selected_ids = selection.GetElementIds()

            if not selected_ids or selected_ids.Count == 0:
                TaskDialog.Show("Aviso", "Selecione elementos no Revit primeiro.")
                return

            param_values = self.get_selected_values()

            if not param_values:
                TaskDialog.Show("Aviso", "Ative ao menos um parametro (toggle marcado).")
                return

            # PRE-CARREGAR selected_ids ANTES do Raise (CRITICO!)
            self.event_handler.param_values = param_values
            self.event_handler.selected_ids = list(selected_ids)

            self.status_text.Text = "Aplicando {} elemento(s)...".format(selected_ids.Count)

            self.external_event.Raise()

        except Exception as e:
            TaskDialog.Show("Erro", "Erro ao aplicar: {}".format(str(e)))

    def load_new_csv(self, sender, args):
        """Carrega CSV externo."""
        csv_file = forms.pick_file(file_ext='csv', title='Selecionar CSV')
        if csv_file:
            self.load_csv(csv_file)

    def save_csv_to_dat(self, sender, args):
        """Salva CSV na pasta DAT."""
        try:
            dat = get_dat_folder(doc)
            if not dat:
                self.status_text.Text = "Projeto nao salvo"
                return
            dat_csv = os.path.join(dat, "{}_data.csv".format(get_project_name(doc)))
            if self.current_csv and self.current_csv != dat_csv:
                shutil.copy2(self.current_csv, dat_csv)
            self.current_csv = dat_csv
            self.status_text.Text = "CSV salvo em DAT"
        except Exception as e:
            self.status_text.Text = "Erro: {}".format(str(e))

    def add_parameter_from_project(self, sender, args):
        """Adiciona parametro do projeto."""
        try:
            param_names = set()

            # SharedParameters
            for sp in FilteredElementCollector(doc).OfClass(SharedParameterElement):
                param_names.add(sp.GetDefinition().Name)

            # Parametros de elementos selecionados
            for eid in uidoc.Selection.GetElementIds():
                elem = doc.GetElement(eid)
                if elem:
                    for p in elem.Parameters:
                        if not p.Definition.Name.startswith('-'):
                            param_names.add(p.Definition.Name)

            available = sorted([p for p in param_names if p not in self.param_controls])
            if not available:
                self.status_text.Text = "Nenhum parametro novo disponivel"
                return

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                selected = forms.SelectFromList.show(
                    available,
                    title="Adicionar Parametros",
                    button_name="Adicionar",
                    multiselect=True
                )
            finally:
                self.Show()

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            if not self.current_csv:
                self.status_text.Text = "Nenhum CSV carregado"
                return

            create_backup(self.current_csv, doc)
            headers, rows = ler_csv_utf8(self.current_csv)
            for p in selected:
                if p not in headers:
                    headers.append(p)
            for row in rows:
                while len(row) < len(headers):
                    row.append('')
            escrever_csv_utf8(self.current_csv, headers, rows)
            self.load_csv(self.current_csv)
            self.status_text.Text = "{} adicionado(s)".format(len(selected))

        except Exception as e:
            import traceback
            print("Erro add_parameter: {}".format(traceback.format_exc()))
            TaskDialog.Show("Erro", str(e))

    def remove_parameter(self, sender, args):
        """Remove parametro do CSV."""
        try:
            if not self.param_controls:
                self.status_text.Text = "Nenhum parametro para remover"
                return

            if not self.current_csv:
                self.status_text.Text = "Nenhum CSV carregado"
                return

            params = sorted(self.param_controls.keys())
            if not params:
                self.status_text.Text = "Lista de parametros vazia"
                return

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                selected = forms.SelectFromList.show(
                    params,
                    title="Remover Parametros",
                    button_name="Remover",
                    multiselect=True
                )
            finally:
                self.Show()

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            # Backup (silencioso)
            create_backup(self.current_csv, doc)

            # Ler CSV atual
            headers, rows = ler_csv_utf8(self.current_csv)
            if not headers:
                self.status_text.Text = "CSV vazio ou erro de leitura"
                return

            # Remover colunas (ordem reversa para manter indices)
            indices = sorted([headers.index(p) for p in selected if p in headers], reverse=True)
            for idx in indices:
                del headers[idx]
                for row in rows:
                    if idx < len(row):
                        del row[idx]

            # Salvar
            if escrever_csv_utf8(self.current_csv, headers, rows):
                self.load_csv(self.current_csv)
                self.status_text.Text = "{} removido(s)".format(len(selected))
            else:
                self.status_text.Text = "Erro ao salvar CSV"

        except Exception as e:
            import traceback
            print("Erro remove_parameter: {}".format(traceback.format_exc()))
            TaskDialog.Show("Erro", str(e))


# ============================================================================
# MAIN
# ============================================================================

try:
    if not doc:
        TaskDialog.Show("Erro", "Nenhum documento ativo")
    else:
        apply_handler = ApplyParametersHandler()
        apply_event = ExternalEvent.Create(apply_handler)
        palette = ParameterPalette(apply_event, apply_handler)

except Exception as e:
    import traceback
    output.print_md("## Erro Critico")
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
    TaskDialog.Show("Erro", str(e))
