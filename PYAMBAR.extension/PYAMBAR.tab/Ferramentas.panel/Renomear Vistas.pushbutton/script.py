# -*- coding: utf-8 -*-
__title__ = "Renomear\nVistas"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.2"
__doc__ = """
_____________________________________________________________________
VERSÃO v4.1 - PADRONIZACAO

NOVIDADES v4.1:
✨ Usar revit.doc/uidoc/app em vez de __revit__

NOVIDADES v4.0:
✨ Logging automático de operações em JSON
✨ Compatibilidade universal (Revit 2019-2026+)
✨ Relatórios detalhados com estatísticas
✨ Fallback robusto para ElementId

FUNCIONALIDADES:
✨ Interface WPF intuitiva
✨ Preview em tempo real
✨ Find & Replace com regex
✨ Prefix/Suffix
✨ Numeração avançada (prefixo, separador, formato)
✨ Renomear Nome, Número ou Ambos (Sheets)

Uso:
1. Tipo: Sheets ou Views
2. Modo: Find & Replace / Prefix/Suffix / Numeração
3. Aplicar em (Sheets): Nome / Número / Ambos
4. Preview → Aplicar
_____________________________________________________________________
"""

import clr
import os
import sys
import re
import codecs
import json
from datetime import datetime

# Adicionar lib ao path
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

clr.AddReference('System')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from pyrevit import forms, script, revit, HOST_APP

from Snippets.core._revit_version_helpers import get_element_id_value
from System.Windows import Window, Visibility
from System.Windows.Controls import ComboBox
from System.Windows.Input import Key, ModifierKeys
from System.Windows.Markup import XamlReader
from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
rvt_year = int(app.VersionNumber)
PATH_SCRIPT = os.path.dirname(__file__)
output = script.get_output()

# Diretório de logs (user folder)
LOG_DIR = os.path.expanduser("~/.pyrevit_rename_logs")
if not os.path.exists(LOG_DIR):
    try:
        os.makedirs(LOG_DIR)
    except:
        LOG_DIR = None

# ==================== LOGGING ====================

def save_operation_log(operation_data):
    """
    Salva log da operação em arquivo JSON.

    Args:
        operation_data (dict): Dados da operação

    Note:
        Salva em ~/.pyrevit_rename_logs/ com timestamp
        Formato: rename_YYYYMMDD_HHMMSS.json
    """
    if not LOG_DIR:
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(LOG_DIR, "rename_{}.json".format(timestamp))

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(operation_data, f, indent=2, ensure_ascii=False)

        output.print_md("📄 **Log salvo:** {}".format(log_file))
    except Exception as e:
        output.print_md("⚠️ Aviso: Não foi possível salvar log: {}".format(str(e)))

# ==================== CLASSES ====================

class NotifyPropertyChangedBase(INotifyPropertyChanged):
    def __init__(self):
        self._property_changed_handlers = []
    
    def add_PropertyChanged(self, handler):
        if handler not in self._property_changed_handlers:
            self._property_changed_handlers.append(handler)
    
    def remove_PropertyChanged(self, handler):
        if handler in self._property_changed_handlers:
            self._property_changed_handlers.remove(handler)
    
    def OnPropertyChanged(self, property_name):
        args = PropertyChangedEventArgs(property_name)
        for handler in self._property_changed_handlers:
            handler(self, args)


class RenameItem(NotifyPropertyChangedBase):
    def __init__(self, element, element_type):
        NotifyPropertyChangedBase.__init__(self)
        self.Element = element
        self.ElementType = element_type
        self._apply = True
        self._new_name = ""
        self._status = ""
        
        try:
            self.OriginalName = element.Name if element.Name else ""
        except:
            self.OriginalName = ""
        
        if element_type == 'Sheet':
            try:
                self.Number = element.SheetNumber if element.SheetNumber else "---"
            except:
                self.Number = "---"
        else:
            self.Number = "---"
    
    def get_Apply(self):
        return self._apply
    
    def set_Apply(self, value):
        if self._apply != value:
            self._apply = value
            self.OnPropertyChanged('Apply')
    
    Apply = property(get_Apply, set_Apply)
    
    def get_NewName(self):
        return self._new_name
    
    def set_NewName(self, value):
        if value is None:
            value = ""
        if self._new_name != value:
            self._new_name = value
            self.OnPropertyChanged('NewName')
    
    NewName = property(get_NewName, set_NewName)
    
    def get_Status(self):
        return self._status
    
    def set_Status(self, value):
        if value is None:
            value = ""
        if self._status != value:
            self._status = value
            self.OnPropertyChanged('Status')
    
    Status = property(get_Status, set_Status)


# ==================== FUNCTIONS ====================

def get_all_sheets(doc):
    collector = FilteredElementCollector(doc).OfClass(ViewSheet)
    sheets = []
    for s in collector:
        try:
            if not s.IsTemplate:
                sheets.append(s)
        except:
            pass
    return sheets


def get_all_views(doc, view_types=None):
    collector = FilteredElementCollector(doc).OfClass(View)
    views = []
    for v in collector:
        try:
            if not v.IsTemplate and v.ViewType != ViewType.DrawingSheet:
                if view_types is None or v.ViewType in view_types:
                    views.append(v)
        except:
            pass
    return views


def validate_unique_names(items, doc, element_type, apply_to):
    """Valida unicidade conforme apply_to: 'name', 'number', 'both'"""
    elements_being_renamed = set([get_element_id_value(item.Element) for item in items if item.Apply])
    
    if element_type == 'Sheet':
        existing = get_all_sheets(doc)
    else:
        existing = get_all_views(doc)
    
    existing = [e for e in existing if get_element_id_value(e) not in elements_being_renamed]
    existing_names = set([e.Name for e in existing if e.Name])
    existing_numbers = set()
    if element_type == 'Sheet':
        existing_numbers = set([e.SheetNumber for e in existing if e.SheetNumber])
    
    new_names = {}
    new_numbers = {}
    all_valid = True
    
    for item in items:
        if not item.Apply:
            item.Status = ""
            continue
        
        new_value = item.NewName.strip()
        
        if not new_value:
            item.Status = "❌ Vazio"
            all_valid = False
        elif apply_to == 'name':
            if new_value == item.OriginalName:
                item.Status = "⚠️ Sem alteração"
            elif new_value in existing_names or new_value in new_names:
                item.Status = "❌ Nome existe"
                all_valid = False
            else:
                item.Status = "✅ OK"
                new_names[new_value] = True
        elif apply_to == 'number':
            if new_value == item.Number:
                item.Status = "⚠️ Sem alteração"
            elif new_value in existing_numbers or new_value in new_numbers:
                item.Status = "❌ Número existe"
                all_valid = False
            else:
                item.Status = "✅ OK"
                new_numbers[new_value] = True
        elif apply_to == 'both':
            # Verificar se há alteração real (nome OU número diferentes)
            name_changed = (new_value != item.OriginalName)
            number_changed = (element_type == 'Sheet' and new_value != item.Number)

            if not name_changed and not number_changed:
                item.Status = "⚠️ Sem alteração"
            elif new_value in existing_names or new_value in new_names:
                item.Status = "❌ Nome existe"
                all_valid = False
            elif new_value in existing_numbers or new_value in new_numbers:
                item.Status = "❌ Número existe"
                all_valid = False
            else:
                item.Status = "✅ OK"
                new_names[new_value] = True
                new_numbers[new_value] = True
    
    return all_valid


def validate_regex(pattern):
    try:
        re.compile(pattern)
        return True, "Regex válido"
    except Exception as e:
        return False, "Regex inválido: {}".format(str(e))


def apply_rename_mode(items, mode, params, apply_to):
    """
    Aplica renomeação conforme modo e apply_to.
    apply_to: 'name', 'number', 'both'
    """
    counter = params.get('start', 1)
    
    for item in items:
        if not item.Apply:
            continue
        
        # CRÍTICO: Usar base correta conforme apply_to
        if apply_to == 'number':
            original = item.Number
        else:
            original = item.OriginalName
        
        try:
            if mode == "Find & Replace":
                param1 = params.get('param1', '')
                param2 = params.get('param2', '')
                use_regex = params.get('use_regex', False)
                
                if not param1:
                    item.NewName = original
                    item.Status = "⚠️ Busca vazia"
                elif use_regex:
                    is_valid, msg = validate_regex(param1)
                    if not is_valid:
                        item.Status = "❌ {}".format(msg)
                        item.NewName = original
                    else:
                        item.NewName = re.sub(param1, param2, original)
                else:
                    item.NewName = original.replace(param1, param2)
            
            elif mode == "Prefix/Suffix":
                prefix = params.get('param1', '')
                suffix = params.get('param2', '')
                
                if not prefix and not suffix:
                    item.NewName = original
                    item.Status = "⚠️ Sem prefixo/sufixo"
                else:
                    item.NewName = "{}{}{}".format(prefix, original, suffix)
            
            elif mode == "Numeração":
                prefix = params.get('prefix', '')
                use_name = params.get('use_name', False)
                separator = params.get('separator', '_')
                number_format = params.get('number_format', '001')
                
                if number_format == '001':
                    num_str = "{:03d}".format(counter)
                elif number_format == '01':
                    num_str = "{:02d}".format(counter)
                else:
                    num_str = str(counter)
                
                parts = []
                if prefix:
                    parts.append(prefix)
                parts.append(num_str)
                if use_name:
                    parts.append(original)
                
                item.NewName = separator.join(parts)
                counter += 1
        
        except Exception as e:
            item.Status = "❌ Erro: {}".format(str(e))
            item.NewName = original


# ==================== UI WINDOW ====================

class RenameWindow(object):
    def __init__(self, xaml_path):
        with codecs.open(xaml_path, 'r', encoding='utf-8') as f:
            xaml_string = f.read()
        
        self.window = XamlReader.Parse(xaml_string)
        
        self.cmbType = self.window.FindName('cmbType')
        self.cmbMode = self.window.FindName('cmbMode')
        self.cmbApplyTo = self.window.FindName('cmbApplyTo')
        self.lblApplyTo = self.window.FindName('lblApplyTo')
        
        self.gridStandardParams = self.window.FindName('gridStandardParams')
        self.txtParam1 = self.window.FindName('txtParam1')
        self.txtParam2 = self.window.FindName('txtParam2')
        self.lblParam1 = self.window.FindName('lblParam1')
        self.lblParam2 = self.window.FindName('lblParam2')
        self.chkRegex = self.window.FindName('chkRegex')
        
        self.borderNumberingParams = self.window.FindName('borderNumberingParams')
        self.txtPrefix = self.window.FindName('txtPrefix')
        self.chkUseName = self.window.FindName('chkUseName')
        self.cmbSeparator = self.window.FindName('cmbSeparator')
        self.txtStart = self.window.FindName('txtStart')
        self.cmbNumberFormat = self.window.FindName('cmbNumberFormat')
        
        self.txtSearch = self.window.FindName('txtSearch')
        self.dgItems = self.window.FindName('dgItems')
        self.txtCounter = self.window.FindName('txtCounter')
        
        self.btnSelectAll = self.window.FindName('btnSelectAll')
        self.btnDeselectAll = self.window.FindName('btnDeselectAll')
        self.btnUndo = self.window.FindName('btnUndo')
        self.btnPreview = self.window.FindName('btnPreview')
        self.btnApply = self.window.FindName('btnApply')
        self.btnClose = self.window.FindName('btnClose')
        
        self.items = ObservableCollection[RenameItem]()
        self.all_items = []
        self.dgItems.ItemsSource = self.items
        
        self.cmbType.SelectionChanged += self.on_type_changed
        self.cmbMode.SelectionChanged += self.on_mode_changed
        self.txtSearch.TextChanged += self.on_search_changed
        self.btnSelectAll.Click += self.on_select_all
        self.btnDeselectAll.Click += self.on_deselect_all
        self.btnUndo.Click += self.on_undo_preview
        self.btnPreview.Click += self.on_preview
        self.btnApply.Click += self.on_apply
        self.btnClose.Click += self.on_close
        self.window.KeyDown += self.on_key_down

        self.load_items()
        self.update_ui_mode()
        self.update_counter()

        # Auto-executar preview ao inicializar (UX improvement)
        self.on_preview(None, None)
    
    def on_key_down(self, sender, args):
        ctrl = args.KeyboardDevice.Modifiers == ModifierKeys.Control
        
        if ctrl and args.Key == Key.P:
            args.Handled = True
            self.on_preview(None, None)
        elif ctrl and args.Key == Key.Enter:
            args.Handled = True
            self.on_apply(None, None)
        elif ctrl and args.Key == Key.Z:
            args.Handled = True
            self.on_undo_preview(None, None)
        elif ctrl and args.Key == Key.A:
            args.Handled = True
            self.on_select_all(None, None)
        elif ctrl and args.Key == Key.D:
            args.Handled = True
            self.on_deselect_all(None, None)
    
    def load_items(self, sender=None, args=None):
        self.items.Clear()
        self.all_items = []
        
        selected_type = self.cmbType.SelectedItem.Content
        
        if selected_type == 'Sheets':
            elements = get_all_sheets(doc)
            element_type = 'Sheet'
        else:
            elements = get_all_views(doc)
            element_type = 'View'
        
        for element in elements:
            item = RenameItem(element, element_type)
            self.all_items.append(item)
            self.items.Add(item)
        
        self.update_counter()
    
    def update_ui_mode(self, sender=None, args=None):
        mode = self.cmbMode.SelectedItem.Content
        selected_type = self.cmbType.SelectedItem.Content
        
        if selected_type == 'Sheets':
            self.cmbApplyTo.Visibility = Visibility.Visible
            self.lblApplyTo.Visibility = Visibility.Visible
        else:
            self.cmbApplyTo.Visibility = Visibility.Collapsed
            self.lblApplyTo.Visibility = Visibility.Collapsed
        
        if mode == "Numeração":
            self.gridStandardParams.Visibility = Visibility.Collapsed
            self.borderNumberingParams.Visibility = Visibility.Visible
            self.chkRegex.Visibility = Visibility.Collapsed
        else:
            self.gridStandardParams.Visibility = Visibility.Visible
            self.borderNumberingParams.Visibility = Visibility.Collapsed
            
            if mode == "Find & Replace":
                self.lblParam1.Content = "Find:"
                self.lblParam2.Content = "Replace:"
                self.chkRegex.Visibility = Visibility.Visible
            elif mode == "Prefix/Suffix":
                self.lblParam1.Content = "Prefixo:"
                self.lblParam2.Content = "Sufixo:"
                self.chkRegex.Visibility = Visibility.Collapsed
    
    def on_type_changed(self, sender, args):
        self.load_items()
        self.update_ui_mode()
        self.update_counter()
    
    def on_mode_changed(self, sender, args):
        self.update_ui_mode()
    
    def on_search_changed(self, sender, args):
        search_text = self.txtSearch.Text.lower()
        self.items.Clear()
        
        for item in self.all_items:
            match = (search_text in item.OriginalName.lower() or 
                    search_text in item.Number.lower() or
                    search_text in item.NewName.lower())
            
            if match or not search_text:
                self.items.Add(item)
        
        self.update_counter()
    
    def on_select_all(self, sender, args):
        for item in self.items:
            item.Apply = True
        self.dgItems.Items.Refresh()
        self.update_counter()
    
    def on_deselect_all(self, sender, args):
        for item in self.items:
            item.Apply = False
        self.dgItems.Items.Refresh()
        self.update_counter()
    
    def on_undo_preview(self, sender, args):
        for item in self.all_items:
            item.NewName = ""
            item.Status = ""
        self.dgItems.Items.Refresh()
    
    def update_counter(self):
        selected = sum(1 for item in self.items if item.Apply)
        total = len(self.items)
        self.txtCounter.Text = "{} de {} selecionados".format(selected, total)
    
    def get_apply_to(self):
        """Retorna 'name', 'number', ou 'both'"""
        selected_type = self.cmbType.SelectedItem.Content
        if selected_type != 'Sheets':
            return 'name'
        
        apply_to_text = self.cmbApplyTo.SelectedItem.Content
        if "Ambos" in apply_to_text:
            return 'both'
        elif "Número" in apply_to_text:
            return 'number'
        else:
            return 'name'
    
    def get_rename_params(self):
        mode = self.cmbMode.SelectedItem.Content
        params = {}
        
        if mode == "Find & Replace":
            params['param1'] = self.txtParam1.Text if self.txtParam1.Text else ""
            params['param2'] = self.txtParam2.Text if self.txtParam2.Text else ""
            params['use_regex'] = self.chkRegex.IsChecked
        
        elif mode == "Prefix/Suffix":
            params['param1'] = self.txtParam1.Text if self.txtParam1.Text else ""
            params['param2'] = self.txtParam2.Text if self.txtParam2.Text else ""
        
        elif mode == "Numeração":
            params['prefix'] = self.txtPrefix.Text if self.txtPrefix.Text else ""
            params['use_name'] = self.chkUseName.IsChecked
            
            sep_text = self.cmbSeparator.SelectedItem.Content
            if "underscore" in sep_text:
                params['separator'] = "_"
            elif "hífen" in sep_text:
                params['separator'] = "-"
            elif "espaço" in sep_text:
                params['separator'] = " "
            else:
                params['separator'] = ""
            
            try:
                params['start'] = int(self.txtStart.Text)
            except:
                params['start'] = 1
            
            fmt_text = self.cmbNumberFormat.SelectedItem.Content
            if "001" in fmt_text:
                params['number_format'] = '001'
            elif "01" in fmt_text:
                params['number_format'] = '01'
            else:
                params['number_format'] = '1'
        
        return params
    
    def on_preview(self, sender, args):
        try:
            mode = self.cmbMode.SelectedItem.Content
            params = self.get_rename_params()
            apply_to = self.get_apply_to()
            
            apply_rename_mode(list(self.all_items), mode, params, apply_to)
            
            selected_type = self.cmbType.SelectedItem.Content
            element_type = 'Sheet' if selected_type == 'Sheets' else 'View'
            validate_unique_names(list(self.all_items), doc, element_type, apply_to)
            
            self.dgItems.Items.Refresh()
            self.update_counter()
            
        except Exception as e:
            output.print_md("❌ **Erro no Preview:** {}".format(str(e)))
            import traceback
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
    
    def on_apply(self, sender, args):
        try:
            selected_type = self.cmbType.SelectedItem.Content
            element_type = 'Sheet' if selected_type == 'Sheets' else 'View'
            apply_to = self.get_apply_to()
            
            is_valid = validate_unique_names(list(self.all_items), doc, element_type, apply_to)
            
            if not is_valid:
                forms.alert('Existem erros de validação.\nCorrija os itens com ❌', 
                          title='Validação', exitscript=False)
                return
            
            to_apply = [item for item in self.all_items 
                       if item.Apply and item.Status in ["✅ OK", "⚠️ Sem alteração"]]
            
            if not to_apply:
                forms.alert('Nenhum item válido selecionado.', exitscript=False)
                return
            
            if not forms.alert(
                'Renomear {} {}?\n\nAção pode ser desfeita (Ctrl+Z no Revit).'.format(
                    len(to_apply), 'item' if len(to_apply) == 1 else 'itens'),
                title='Confirmar', ok=False, yes=True, no=True):
                return
            
            tg = TransactionGroup(doc, 'Renomear Sheets/Views')
            tg.Start()
            t = Transaction(doc, 'Renomear Lote')
            t.Start()
            
            try:
                success_count = 0
                errors = []
                renamed_items = []

                for item in to_apply:
                    try:
                        changed = False
                        if apply_to == 'name':
                            if item.NewName != item.OriginalName:
                                item.Element.Name = item.NewName
                                success_count += 1
                                changed = True
                        elif apply_to == 'number' and element_type == 'Sheet':
                            if item.NewName != item.Number:
                                item.Element.SheetNumber = item.NewName
                                success_count += 1
                                changed = True
                        elif apply_to == 'both' and element_type == 'Sheet':
                            if item.NewName != item.OriginalName:
                                item.Element.Name = item.NewName
                                item.Element.SheetNumber = item.NewName
                                success_count += 1
                                changed = True

                        if changed:
                            renamed_items.append({
                                "original": item.OriginalName,
                                "new": item.NewName,
                                "number": item.Number,
                                "element_id": get_element_id_value(item.Element)
                            })
                    except Exception as e:
                        errors.append((item.OriginalName, str(e)))
                        item.Status = "❌ {}".format(str(e)[:50])
                
                t.Commit()
                tg.Assimilate()

                # Salvar log da operação
                mode = self.cmbMode.SelectedItem.Content
                log_data = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "document": doc.Title,
                    "element_type": element_type,
                    "mode": mode,
                    "apply_to": apply_to,
                    "success_count": success_count,
                    "error_count": len(errors),
                    "renamed_items": renamed_items
                }
                save_operation_log(log_data)

                msg = '✅ {} {} renomeado{}.'.format(
                    success_count,
                    'item' if success_count == 1 else 'itens',
                    '' if success_count == 1 else 's')
                
                if errors:
                    msg += '\n\n⚠️ {} erro{}:'.format(
                        len(errors), '' if len(errors) == 1 else 's')
                    for orig, err in errors[:5]:
                        msg += '\n• {}: {}'.format(orig[:30], err[:50])
                    if len(errors) > 5:
                        msg += '\n• ... +{} erros'.format(len(errors) - 5)
                
                forms.alert(msg, title='Resultado')
                
                if errors:
                    output.print_md("## ⚠️ Relatório de Erros\n")
                    for orig, err in errors:
                        output.print_md("- **{}**: {}".format(orig, err))
                
                self.load_items()
                
            except Exception as e:
                t.RollBack()
                tg.RollBack()
                raise
        
        except Exception as e:
            output.print_md("❌ **Erro:** {}".format(str(e)))
            import traceback
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
    
    def on_close(self, sender, args):
        self.window.Close()
    
    def show(self):
        self.window.ShowDialog()


# ==================== MAIN ====================

def main():
    try:
        xaml_path = os.path.join(PATH_SCRIPT, 'UI.xaml')
        
        if not os.path.exists(xaml_path):
            output.print_md("❌ Arquivo UI.xaml não encontrado")
            return
        
        window = RenameWindow(xaml_path)
        window.show()
        
    except Exception as e:
        output.print_md("❌ **Erro fatal:** {}".format(str(e)))
        import traceback
        output.print_md("```python\n{}\n```".format(traceback.format_exc()))


if __name__ == '__main__':
    main()
