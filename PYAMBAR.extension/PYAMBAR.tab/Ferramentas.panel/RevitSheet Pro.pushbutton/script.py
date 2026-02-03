# -*- coding: utf-8 -*-
__title__ = "RevitSheet\nPro"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "2.6"
__doc__ = """
_____________________________________________________________________
Descrição:
Editor profissional de schedules do Revit com interface Excel-like.
Recursos: Undo/Redo ilimitado, Import/Export CSV, Find & Replace com
seleção de coluna, validação visual de campos read-only.

Uso:
1. Selecione um schedule para editar
2. Modifique os dados na grid (campos cinzas são somente leitura)
3. Use Find & Replace para substituições em massa
4. Use Preview para verificar alterações
5. Aplique as mudanças no Revit

Atalhos:
- Ctrl+Z: Undo
- Ctrl+Y: Redo  
- Ctrl+F: Find & Replace
- Ctrl+S: Export CSV

CHANGELOG v2.6 (22.10.2025):
- ✅ CORRIGIDO: XAML inline substituído por ui_find_replace.xaml
- ✅ CORRIGIDO: IOError "sintaxe do nome do arquivo" resolvido
- ✅ Estrutura de arquivos corrigida conforme padrões pyRevit
- ✅ Diálogo Find & Replace agora carrega corretamente

CHANGELOG v2.5 (22.10.2025):
- ✅ CORRIGIDO: Script.py ausente (era por isso que nada acontecia!)
- ✅ CORRIGIDO: Find & Replace agora força refresh completo da grid
- ✅ CORRIGIDO: Dialog ShowDialog() retorna bool corretamente
- ✅ Removido botão Export Excel desnecessário
- ✅ Campos read-only com fundo cinza + cursor bloqueado
- ✅ Banner informativo sobre campos bloqueados
- ✅ Logs detalhados no output para debug
_____________________________________________________________________
Última atualização: 22.10.2025 - v2.6 STABLE
"""

# IMPORTS
import clr
import sys
import os

# Add references
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('System.Windows.Forms')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from System.Windows import *
from System.Windows.Controls import *
from System.Windows.Data import *
from System.Windows.Input import *
from System.Windows.Media import *
from System.Collections.Generic import List
from System import Action

# pyRevit imports
from pyrevit import revit, forms, script

# Add lib path and import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from RevitSheetPro import DataManager, DataItem, UndoRedoManager, ChangeCommand, BatchChangeCommand
from RevitSheetPro.data_manager import get_element_id_value

# Global variables
doc = revit.doc
output = script.get_output()


# ==================== HELPER FUNCTIONS ====================

def is_valid_element_id(element_id):
    """Check if ElementId is valid (compatible with all Revit versions)"""
    try:
        return element_id.Value != -1
    except AttributeError:
        try:
            return element_id.IntegerValue != -1
        except:
            try:
                return element_id != ElementId.InvalidElementId
            except:
                return False


# ==================== FIND/REPLACE DIALOG ====================

class FindReplaceDialog(forms.WPFWindow):
    """Custom Find and Replace dialog with column selection - v2.6 FIXED"""
    
    def __init__(self, columns):
        """Initialize dialog with available columns"""
        self.columns = columns
        self.find_text = ""
        self.replace_text = ""
        self.selected_column = "All Columns"
        self.case_sensitive = False
        self.dialog_result = False
        
        # Load XAML from file - CORRIGIDO v2.6
        xaml_file = script.get_bundle_file('ui_find_replace.xaml')
        forms.WPFWindow.__init__(self, xaml_file)
        
        # Setup ComboBox
        self.cmbColumn.Items.Add("All Columns")
        for col in columns:
            self.cmbColumn.Items.Add(col)
        self.cmbColumn.SelectedIndex = 0
        
        # Setup event handlers
        self.btnReplace.Click += self.on_replace_click
        self.btnCancel.Click += self.on_cancel_click
        
        # Focus on find textbox
        self.txtFind.Focus()
    
    def on_replace_click(self, sender, e):
        """Handle Replace button click"""
        self.find_text = self.txtFind.Text.strip()
        self.replace_text = self.txtReplace.Text  # Don't strip replace text
        self.selected_column = str(self.cmbColumn.SelectedItem)
        self.case_sensitive = bool(self.chkCaseSensitive.IsChecked)
        
        if not self.find_text:
            forms.alert("⚠️ Please enter text to find")
            self.txtFind.Focus()
            return
        
        self.dialog_result = True
        self.DialogResult = True
        self.Close()
    
    def on_cancel_click(self, sender, e):
        """Handle Cancel button click"""
        self.dialog_result = False
        self.DialogResult = False
        self.Close()


# ==================== REVIT DATA EXTRACTION ====================

class ScheduleDataExtractor:
    """Extracts and processes schedule data from Revit"""
    
    @staticmethod
    def get_all_schedules():
        """Get all valid schedules from document"""
        schedules = []
        collector = FilteredElementCollector(doc).OfClass(ViewSchedule)
        
        for schedule in collector:
            if not schedule.IsTitleblockRevisionSchedule and \
               schedule.Definition and \
               schedule.Definition.IsValidObject:
                schedules.append(schedule)
        
        return sorted(schedules, key=lambda s: s.Name)
    
    @staticmethod
    def extract_schedule_data(schedule):
        """Extract complete data from schedule"""
        schedule_def = schedule.Definition
        
        # Get field information
        fields_info = []
        for i in range(schedule_def.GetFieldCount()):
            field = schedule_def.GetField(i)
            try:
                schedulable_field = field.GetSchedulableField()
                fields_info.append({
                    'index': i,
                    'name': field.GetName(),
                    'schedulable': schedulable_field,
                    'hidden': field.IsHidden,
                    'can_edit': not field.IsCalculatedField,
                    'type': 'text'
                })
            except:
                fields_info.append({
                    'index': i,
                    'name': field.GetName(),
                    'schedulable': None,
                    'hidden': field.IsHidden,
                    'can_edit': False,
                    'type': 'calculated'
                })
        
        # Get elements in schedule
        collector = FilteredElementCollector(doc, schedule.Id)
        element_ids = list(collector.ToElementIds())
        
        # Build data matrix
        data_matrix = []
        for elem_id in element_ids:
            element = doc.GetElement(elem_id)
            row_data = []
            
            for field_info in fields_info:
                if field_info['schedulable']:
                    param = ScheduleDataExtractor._get_parameter(element, field_info['schedulable'])
                    value = ScheduleDataExtractor._get_param_value(param) if param else ""
                    storage_type = param.StorageType if param else None
                    is_readonly = param.IsReadOnly if param else True
                    
                    row_data.append({
                        'value': value,
                        'param': param,
                        'storage_type': storage_type,
                        'readonly': is_readonly,
                        'element': element
                    })
                else:
                    row_data.append({
                        'value': field_info.get('name', ''),
                        'param': None,
                        'storage_type': None,
                        'readonly': True,
                        'element': element
                    })
            
            data_matrix.append(row_data)
        
        return element_ids, fields_info, data_matrix
    
    @staticmethod
    def _get_parameter(element, schedulable_field):
        """Get parameter from element"""
        try:
            param_id = schedulable_field.ParameterId
            param = element.get_Parameter(param_id)
            if param:
                return param
        except:
            pass
        
        try:
            field_name = schedulable_field.GetName(doc)
            return element.LookupParameter(field_name)
        except:
            return None
    
    @staticmethod
    def _get_param_value(param):
        """Extract parameter value as string - Revit 2026 compatible"""
        if not param or not param.HasValue:
            return ""
        
        storage = param.StorageType
        
        if storage == StorageType.String:
            return param.AsString() or ""
        elif storage == StorageType.Integer:
            return str(param.AsInteger())
        elif storage == StorageType.Double:
            return param.AsValueString() or str(param.AsDouble())
        elif storage == StorageType.ElementId:
            elem_id = param.AsElementId()
            if elem_id and is_valid_element_id(elem_id):
                elem = doc.GetElement(elem_id)
                return elem.Name if elem else str(get_element_id_value(elem_id))
        
        return ""


# ==================== MAIN WINDOW ====================

class RevitSheetProWindow(forms.WPFWindow):
    """Main window for RevitSheet Pro - v2.6 STABLE"""
    
    def __init__(self, schedule):
        """Initialize window with schedule data"""
        self.schedule = schedule
        self.data_manager = DataManager()
        self.current_cell_value = None
        
        # Load XAML
        xaml_path = script.get_bundle_file('ui.xaml')
        forms.WPFWindow.__init__(self, xaml_path)
        
        # Extract data
        self._load_schedule_data()
        
        # Setup UI
        self._setup_ui()
        self._setup_event_handlers()
        
        # Initial UI update
        self._update_ui_state()
    
    def _load_schedule_data(self):
        """Load schedule data into data manager"""
        output.print_md("**Loading schedule data...**")
        
        # Extract data
        self.element_ids, self.fields_info, self.data_matrix = \
            ScheduleDataExtractor.extract_schedule_data(self.schedule)
        
        # Load into data manager
        self.data_manager.LoadData(self.element_ids, self.fields_info, self.data_matrix)
        
        # Setup undo/redo callback
        self.data_manager.undo_manager.on_state_changed = self._on_undo_state_changed
        
        output.print_md("✅ Loaded {} elements with {} fields".format(
            len(self.element_ids), len(self.fields_info)
        ))
    
    def _setup_ui(self):
        """Setup UI components"""
        # Update header
        self.scheduleNameText.Text = self.schedule.Name
        self.elementCountText.Text = "{} elements".format(len(self.element_ids))
        self.fieldCountText.Text = "{} fields".format(
            len([f for f in self.fields_info if not f['hidden']])
        )
        
        # Setup DataGrid columns with visual styling
        self._setup_datagrid_columns()
        
        # Setup filter ComboBox
        self.cmbFilterColumn.Items.Add("All Columns")
        for field in self.fields_info:
            if not field['hidden']:
                self.cmbFilterColumn.Items.Add(field['name'])
        self.cmbFilterColumn.SelectedIndex = 0
        
        # Convert items to list for DataGrid
        items_list = List[object]()
        for item in self.data_manager.items:
            items_list.Add(item)
        
        # Bind data to grid
        self.mainDataGrid.ItemsSource = items_list
        
        # Setup selection changed handler
        self.mainDataGrid.SelectionChanged += self._on_selection_changed
    
    def _setup_datagrid_columns(self):
        """Create DataGrid columns with read-only visual styling"""
        
        # Style for read-only cells
        readonly_style = Style(TargetType=DataGridCell)
        readonly_style.Setters.Add(Setter(
            DataGridCell.BackgroundProperty, 
            SolidColorBrush(Color.FromRgb(245, 245, 245))  # Cinza claro
        ))
        readonly_style.Setters.Add(Setter(
            DataGridCell.ForegroundProperty, 
            SolidColorBrush(Color.FromRgb(117, 117, 117))  # Texto cinza
        ))
        readonly_style.Setters.Add(Setter(
            DataGridCell.CursorProperty, 
            Cursors.No  # Cursor bloqueado
        ))
        
        # Style for editable cells
        editable_style = Style(TargetType=DataGridCell)
        editable_style.Setters.Add(Setter(
            DataGridCell.CursorProperty, 
            Cursors.IBeam
        ))
        
        for field_info in self.fields_info:
            if field_info['hidden']:
                continue
            
            # Create column
            column = DataGridTextColumn()
            column.Header = field_info['name']
            column.Width = DataGridLength(150)
            
            # Create binding
            binding = Binding("[{}]".format(field_info['name']))
            binding.Mode = BindingMode.TwoWay
            binding.UpdateSourceTrigger = UpdateSourceTrigger.LostFocus
            
            column.Binding = binding
            
            # Determine if read-only
            is_readonly = field_info.get('readonly', False) or not field_info.get('can_edit', True)
            column.IsReadOnly = is_readonly
            
            # Apply visual style
            column.CellStyle = readonly_style if is_readonly else editable_style
            
            # Add to grid
            self.mainDataGrid.Columns.Add(column)
    
    def _setup_event_handlers(self):
        """Setup all event handlers"""
        # File operations
        self.btnExportCsv.Click += self._on_export_csv
        self.btnImportCsv.Click += self._on_import_csv
        
        # Edit operations
        self.btnUndo.Click += self._on_undo
        self.btnRedo.Click += self._on_redo
        
        # Data operations
        self.btnFindReplace.Click += self._on_find_replace
        self.btnFillEmpty.Click += self._on_fill_empty
        self.btnFillColumn.Click += self._on_fill_column
        self.btnClearSelected.Click += self._on_clear_selected
        
        # Revit operations
        self.btnPreview.Click += self._on_preview_changes
        self.btnApply.Click += self._on_apply_changes
        
        # Filter operations
        self.txtQuickFilter.TextChanged += self._on_filter_changed
        self.cmbFilterColumn.SelectionChanged += self._on_filter_changed
        self.chkShowModifiedOnly.Checked += self._on_filter_changed
        self.chkShowModifiedOnly.Unchecked += self._on_filter_changed
        
        # DataGrid events
        self.mainDataGrid.BeginningEdit += self._on_beginning_edit
        self.mainDataGrid.CellEditEnding += self._on_cell_edit_ending
    
    def _on_beginning_edit(self, sender, e):
        """Store value before editing"""
        row = e.Row.DataContext
        col_index = e.Column.DisplayIndex
        field_info = [f for f in self.fields_info if not f['hidden']][col_index]
        field_name = field_info['name']
        
        if hasattr(row, 'GetValue'):
            self.current_cell_value = row.GetValue(field_name)
        else:
            self.current_cell_value = None
    
    def _on_cell_edit_ending(self, sender, e):
        """Handle cell edit completion"""
        if e.EditAction == DataGridEditAction.Cancel:
            return
        
        # Get edited value
        element = e.EditingElement
        if isinstance(element, TextBox):
            new_value = element.Text
        else:
            new_value = str(element)
        
        # Get cell info
        row = e.Row.DataContext
        col_index = e.Column.DisplayIndex
        
        # Get field info
        field_info = [f for f in self.fields_info if not f['hidden']][col_index]
        field_name = field_info['name']
        
        # Get old value
        old_value = self.current_cell_value
        if old_value is None:
            if hasattr(row, 'GetValue'):
                old_value = row.GetValue(field_name)
            else:
                old_value = ""
        
        # Create and execute change command if value changed
        if str(old_value) != str(new_value):
            if hasattr(row, 'SetValue'):
                command = ChangeCommand(row, field_name, old_value, new_value)
                self.data_manager.undo_manager.ExecuteCommand(command)
                self._update_ui_state()
    
    def _on_selection_changed(self, sender, e):
        """Handle selection change"""
        selected_count = self.mainDataGrid.SelectedCells.Count
        if selected_count == 0:
            self.txtSelectionInfo.Text = "No selection"
        elif selected_count == 1:
            self.txtSelectionInfo.Text = "1 cell selected"
        else:
            self.txtSelectionInfo.Text = "{} cells selected".format(selected_count)
    
    def _on_filter_changed(self, sender, e):
        """Apply filters to DataGrid"""
        # Get filter settings
        filter_text = self.txtQuickFilter.Text.lower()
        filter_column = self.cmbFilterColumn.SelectedItem
        show_modified_only = self.chkShowModifiedOnly.IsChecked
        
        # Create filtered list
        filtered_items = List[object]()
        
        for item in self.data_manager.items:
            # Check modified filter
            if show_modified_only and not item.IsModified:
                continue
            
            # Check text filter
            if filter_text:
                if filter_column == "All Columns":
                    # Search all fields
                    found = False
                    for field in self.fields_info:
                        if not field['hidden']:
                            value = str(item.GetValue(field['name']) or "").lower()
                            if filter_text in value:
                                found = True
                                break
                    if not found:
                        continue
                else:
                    # Search specific field
                    value = str(item.GetValue(filter_column) or "").lower()
                    if filter_text not in value:
                        continue
            
            filtered_items.Add(item)
        
        # Update grid
        self.mainDataGrid.ItemsSource = filtered_items
    
    def _on_undo(self, sender, e):
        """Handle undo operation"""
        if self.data_manager.undo_manager.Undo():
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Undo completed"
    
    def _on_redo(self, sender, e):
        """Handle redo operation"""
        if self.data_manager.undo_manager.Redo():
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Redo completed"
    
    def _on_undo_state_changed(self):
        """Handle undo/redo state change"""
        self._update_ui_state()
    
    def _refresh_grid(self):
        """Refresh DataGrid - FORCE COMPLETE UPDATE"""
        # Create new list
        items_list = List[object]()
        for item in self.data_manager.items:
            items_list.Add(item)
        
        # Clear and rebind
        self.mainDataGrid.ItemsSource = None
        self.mainDataGrid.Items.Refresh()
        self.mainDataGrid.ItemsSource = items_list
        
        # Force visual update
        self.mainDataGrid.UpdateLayout()
    
    def _on_export_csv(self, sender, e):
        """Export to CSV file"""
        file_path = forms.save_file(
            file_ext='csv',
            default_name='{}_export.csv'.format(self.schedule.Name)
        )
        
        if not file_path:
            return
        
        success, error = self.data_manager.ExportToCSV(file_path)
        
        if success:
            forms.alert("✅ Export completed successfully!\n\n{}".format(file_path))
            self.statusText.Text = "Exported to CSV"
        else:
            forms.alert("❌ Export failed:\n{}".format(error), exitscript=False)
    
    def _on_import_csv(self, sender, e):
        """Import from CSV file"""
        file_path = forms.pick_file(file_ext='csv')
        
        if not file_path:
            return
        
        # Confirm import
        result = forms.alert(
            "Import will overwrite matching cells.\nContinue?",
            yes=True, no=True
        )
        
        if not result:
            return
        
        # Create element ID map
        elem_map = {str(get_element_id_value(eid)): i for i, eid in enumerate(self.element_ids)}
        
        # Import data
        success, result = self.data_manager.ImportFromCSV(file_path, elem_map)
        
        if success:
            if isinstance(result, int) and result > 0:
                forms.alert("✅ Import completed!\n\n{} changes applied.".format(result))
                self._refresh_grid()
                self._update_ui_state()
                self.statusText.Text = "Imported {} changes from CSV".format(result)
            else:
                forms.alert("ℹ️ No changes found in CSV file.")
        else:
            forms.alert("❌ Import failed:\n{}".format(result), exitscript=False)
    
    def _on_find_replace(self, sender, e):
        """Show find and replace dialog - v2.6 FIXED"""
        try:
            output.print_md("---")
            output.print_md("## 🔍 Find & Replace")
            
            # Get visible column names
            visible_columns = [f['name'] for f in self.fields_info if not f['hidden']]
            
            output.print_md("**Available columns:** {}".format(len(visible_columns)))
            
            # Create and show dialog - v2.6: Now loads from ui_find_replace.xaml
            dialog = FindReplaceDialog(visible_columns)
            
            # Show dialog and wait for result
            dialog_result = dialog.ShowDialog()
            
            output.print_md("**Dialog result:** {}".format(dialog_result))
            
            # Check if user clicked Replace
            if not dialog.dialog_result:
                output.print_md("⚠️ **Cancelled by user**")
                return
            
            # Get dialog values
            find_text = dialog.find_text
            replace_text = dialog.replace_text
            selected_column = dialog.selected_column
            case_sensitive = dialog.case_sensitive
            
            # Determine column name
            column_name = None if selected_column == "All Columns" else selected_column
            
            # Log operation
            output.print_md("**Search scope:** {}".format(selected_column))
            output.print_md("**Find:** '{}'".format(find_text))
            output.print_md("**Replace with:** '{}'".format(replace_text))
            output.print_md("**Case sensitive:** {}".format(case_sensitive))
            
            # Perform find and replace
            count = self.data_manager.FindAndReplace(
                find_text, replace_text, column_name,
                use_regex=False, case_sensitive=case_sensitive
            )
            
            output.print_md("**Matches found:** {}".format(count))
            
            if count > 0:
                # CRITICAL: Force complete refresh
                self._refresh_grid()
                self._update_ui_state()
                
                # Show success
                forms.alert("✅ Replaced {} occurrence(s)!".format(count))
                self.statusText.Text = "Replaced {} items".format(count)
                output.print_md("✅ **SUCCESS: Replaced {} occurrences**".format(count))
            else:
                forms.alert("ℹ️ No matches found")
                output.print_md("⚠️ **No matches found**")
            
        except Exception as ex:
            output.print_md("❌ **ERROR in Find & Replace:**")
            output.print_md("```")
            import traceback
            output.print_md(traceback.format_exc())
            output.print_md("```")
            forms.alert("❌ Error: {}".format(str(ex)))
    
    def _on_fill_empty(self, sender, e):
        """Fill empty cells in selected columns"""
        selected_cells = self.mainDataGrid.SelectedCells
        if not selected_cells:
            forms.alert("⚠️ Please select cells first")
            return
        
        # Get unique columns
        columns = set()
        for cell in selected_cells:
            col_index = cell.Column.DisplayIndex
            field_info = [f for f in self.fields_info if not f['hidden']][col_index]
            columns.add(field_info['name'])
        
        # Get fill value
        fill_value = forms.ask_for_string(
            prompt="Enter value to fill empty cells:",
            title="Fill Empty Cells"
        )
        
        if fill_value is None:
            return
        
        # Fill empty cells
        total_count = 0
        for column_name in columns:
            count = self.data_manager.FillEmpty(column_name, fill_value)
            total_count += count
        
        if total_count > 0:
            forms.alert("✅ Filled {} empty cell(s)".format(total_count))
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Filled {} cells".format(total_count)
        else:
            forms.alert("ℹ️ No empty cells found")
    
    def _on_fill_column(self, sender, e):
        """Fill entire column with value"""
        selected_cells = self.mainDataGrid.SelectedCells
        if not selected_cells:
            forms.alert("⚠️ Please select a column first")
            return
        
        # Get column
        col_index = selected_cells[0].Column.DisplayIndex
        field_info = [f for f in self.fields_info if not f['hidden']][col_index]
        column_name = field_info['name']
        
        # Confirm action
        result = forms.alert(
            "Replace ALL values in column '{}'?".format(column_name),
            yes=True, no=True
        )
        
        if not result:
            return
        
        # Get fill value
        fill_value = forms.ask_for_string(
            prompt="Enter value for entire column:",
            title="Fill Column"
        )
        
        if fill_value is None:
            return
        
        # Fill column
        count = self.data_manager.FillColumn(column_name, fill_value)
        
        if count > 0:
            forms.alert("✅ Updated {} cell(s)".format(count))
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Filled column with {} changes".format(count)
    
    def _on_clear_selected(self, sender, e):
        """Clear selected cells"""
        selected_cells = self.mainDataGrid.SelectedCells
        if not selected_cells:
            return
        
        # Create commands for clearing
        commands = []
        
        for cell in selected_cells:
            item = cell.Item
            col_index = cell.Column.DisplayIndex
            
            field_info = [f for f in self.fields_info if not f['hidden']][col_index]
            field_name = field_info['name']
            
            if not field_info.get('readonly') and field_info.get('can_edit'):
                if hasattr(item, 'GetValue'):
                    current_value = item.GetValue(field_name)
                    
                    if current_value:
                        cmd = ChangeCommand(item, field_name, current_value, "")
                        commands.append(cmd)
        
        if commands:
            batch = BatchChangeCommand(commands)
            self.data_manager.undo_manager.ExecuteCommand(batch)
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Cleared {} cell(s)".format(len(commands))
    
    def _on_preview_changes(self, sender, e):
        """Preview pending changes"""
        modified_items = self.data_manager.GetModifiedItems()
        
        if not modified_items:
            forms.alert("ℹ️ No changes to preview")
            return
        
        # Build preview text
        preview_lines = ["**Preview of Changes:**\n"]
        
        for item in modified_items[:20]:
            elem_id_value = item.ElementIdValue
            preview_lines.append("**Element {}:**".format(elem_id_value))
            
            for field in self.fields_info:
                if not field['hidden']:
                    field_name = field['name']
                    old_value = item.GetOriginalValue(field_name)
                    new_value = item.GetValue(field_name)
                    
                    if str(old_value) != str(new_value):
                        preview_lines.append("  {} | {} → {}".format(
                            field_name,
                            old_value[:30] if old_value else "(empty)",
                            new_value[:30] if new_value else "(empty)"
                        ))
            
            preview_lines.append("")
        
        if len(modified_items) > 20:
            preview_lines.append("... and {} more items".format(len(modified_items) - 20))
        
        # Show preview
        output.print_md("\n".join(preview_lines))
        
        # Enable apply button
        self.btnApply.IsEnabled = True
        self.statusText.Text = "Preview generated - {} items modified".format(len(modified_items))
    
    def _on_apply_changes(self, sender, e):
        """Apply changes to Revit"""
        modified_items = self.data_manager.GetModifiedItems()
        
        if not modified_items:
            forms.alert("ℹ️ No changes to apply")
            return
        
        # Confirm
        mod_count = self.data_manager.GetModificationCount()
        result = forms.alert(
            "Apply {} modifications to {} elements in Revit?\n\n"
            "⚠️ This action cannot be undone within this tool.".format(
                mod_count, len(modified_items)
            ),
            yes=True, no=True
        )
        
        if not result:
            return
        
        # Apply changes in transaction
        success_count = 0
        errors = []
        
        with revit.Transaction("RevitSheet Pro - Apply Changes"):
            for item in modified_items:
                elem_id = item.ElementId
                element = doc.GetElement(elem_id)
                
                if not element:
                    errors.append("Element {} not found".format(item.ElementIdValue))
                    continue
                
                for field in self.fields_info:
                    if field['hidden'] or not field.get('can_edit'):
                        continue
                    
                    field_name = field['name']
                    old_value = item.GetOriginalValue(field_name)
                    new_value = item.GetValue(field_name)
                    
                    if str(old_value) == str(new_value):
                        continue
                    
                    # Find corresponding parameter
                    elem_index = self.element_ids.index(elem_id)
                    field_index = field['index']
                    param_info = self.data_matrix[elem_index][field_index]
                    param = param_info['param']
                    
                    if not param or param.IsReadOnly:
                        errors.append("Parameter '{}' is read-only for element {}".format(
                            field_name, item.ElementIdValue
                        ))
                        continue
                    
                    try:
                        # Set parameter value
                        storage = param.StorageType
                        
                        if storage == StorageType.String:
                            param.Set(new_value)
                        elif storage == StorageType.Integer:
                            param.Set(int(float(new_value)))
                        elif storage == StorageType.Double:
                            param.Set(float(new_value))
                        else:
                            errors.append("Unsupported type for '{}' in element {}".format(
                                field_name, item.ElementIdValue
                            ))
                            continue
                        
                        success_count += 1
                        
                    except Exception as ex:
                        errors.append("Error setting '{}' in element {}: {}".format(
                            field_name, item.ElementIdValue, str(ex)
                        ))
        
        # Show results
        if success_count > 0:
            message = "✅ Successfully applied {} changes!".format(success_count)
            if errors:
                message += "\n\n⚠️ {} errors occurred:\n{}".format(
                    len(errors), "\n".join(errors[:5])
                )
            
            forms.alert(message)
            
            # Reset modified state
            for item in modified_items:
                item._original_values = dict(item._field_values)
                item._modified = False
            
            # Clear undo history
            self.data_manager.undo_manager.Clear()
            self._refresh_grid()
            self._update_ui_state()
            
            self.statusText.Text = "Applied {} changes to Revit".format(success_count)
        else:
            forms.alert("❌ No changes were applied.\n\nErrors:\n{}".format(
                "\n".join(errors[:10])
            ))
    
    def _update_ui_state(self):
        """Update UI based on current state"""
        # Update undo/redo buttons
        self.btnUndo.IsEnabled = self.data_manager.undo_manager.CanUndo()
        self.btnRedo.IsEnabled = self.data_manager.undo_manager.CanRedo()
        
        # Update undo info text
        undo_count = self.data_manager.undo_manager.GetUndoCount()
        redo_count = self.data_manager.undo_manager.GetRedoCount()
        self.txtUndoInfo.Text = "History: {} undo | {} redo".format(undo_count, redo_count)
        
        # Update modification count
        mod_count = self.data_manager.GetModificationCount()
        if mod_count > 0:
            self.txtModificationCount.Text = "{} modifications pending".format(mod_count)
            self.txtModificationCount.Foreground = SolidColorBrush(Color.FromRgb(255, 152, 0))
            self.btnApply.IsEnabled = True
        else:
            self.txtModificationCount.Text = "No modifications"
            self.txtModificationCount.Foreground = SolidColorBrush(Color.FromRgb(117, 117, 117))
            self.btnApply.IsEnabled = False
        
        # Update performance indicator
        item_count = len(self.data_manager.items)
        if item_count < 1000:
            self.performanceText.Text = "Performance: Optimal"
            self.performanceText.Foreground = SolidColorBrush(Color.FromRgb(76, 175, 80))
        elif item_count < 5000:
            self.performanceText.Text = "Performance: Good"
            self.performanceText.Foreground = SolidColorBrush(Color.FromRgb(255, 193, 7))
        else:
            self.performanceText.Text = "Performance: Large dataset"
            self.performanceText.Foreground = SolidColorBrush(Color.FromRgb(255, 152, 0))


# ==================== MAIN EXECUTION ====================

def main():
    """Main execution function"""
    output.print_md("## 🚀 RevitSheet Pro v2.6 STABLE - Enterprise Schedule Editor")
    output.print_md("---")
    
    # Get all schedules
    schedules = ScheduleDataExtractor.get_all_schedules()
    
    if not schedules:
        forms.alert("❌ No schedules found in the current document.", exitscript=True)
    
    # Select schedule
    schedule_dict = {s.Name: s for s in schedules}
    schedule_names = [s.Name for s in schedules]
    
    selected_name = forms.SelectFromList.show(
        schedule_names,
        title="Select Schedule to Edit",
        button_name="Open in RevitSheet Pro",
        multiselect=False
    )
    
    if not selected_name:
        output.print_md("❌ **Cancelled:** No schedule selected")
        return
    
    selected_schedule = schedule_dict[selected_name]
    
    output.print_md("**Opening:** {}".format(selected_schedule.Name))
    
    # Check if schedule has elements
    collector = FilteredElementCollector(doc, selected_schedule.Id)
    if collector.GetElementCount() == 0:
        forms.alert(
            "⚠️ Selected schedule has no elements.\n\n"
            "Please select a schedule with data.",
            exitscript=True
        )
    
    # Launch editor window
    try:
        window = RevitSheetProWindow(selected_schedule)
        window.ShowDialog()
        
        output.print_md("---")
        output.print_md("✅ **Session completed successfully**")
        
    except Exception as ex:
        output.print_md("❌ **Error:** {}".format(str(ex)))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


# ==================== RUN ====================
if __name__ == '__main__':
    main()
