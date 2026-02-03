# -*- coding: utf-8 -*-
"""
Data Manager Module for RevitSheet Pro
Handles data operations, undo/redo, and state management
Compatible with Revit 2023+ API
"""

import clr
clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')

from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs
from System import EventHandler
from Autodesk.Revit.DB import ElementId


def get_element_id_value(element_id):
    """Get ElementId value compatible with all Revit versions"""
    if hasattr(element_id, 'Value'):
        # Revit 2024+ uses .Value
        return element_id.Value
    elif hasattr(element_id, 'IntegerValue'):
        # Older versions use .IntegerValue
        return element_id.IntegerValue
    else:
        # Fallback to int conversion
        return int(element_id.ToString())


class DataItem(object):
    """Data item with change tracking - simplified for IronPython"""
    
    def __init__(self, element_id, field_values, field_info):
        self._element_id = element_id
        self._field_values = field_values  # Dictionary
        self._field_info = field_info
        self._original_values = dict(field_values)
        self._modified = False
        self._errors = {}
    
    @property
    def ElementId(self):
        return self._element_id
    
    @property
    def ElementIdValue(self):
        """Get the numeric value of ElementId for all Revit versions"""
        return get_element_id_value(self._element_id)
    
    @property
    def IsModified(self):
        return self._modified
    
    def GetValue(self, field_name):
        """Get field value"""
        return self._field_values.get(field_name, "")
    
    def SetValue(self, field_name, value):
        """Set field value with change tracking"""
        old_value = self._field_values.get(field_name)
        if str(old_value) != str(value):
            self._field_values[field_name] = value
            self._modified = self._field_values != self._original_values
            return True
        return False
    
    def GetOriginalValue(self, field_name):
        """Get original value before modifications"""
        return self._original_values.get(field_name, "")
    
    def ResetToOriginal(self):
        """Reset all values to original"""
        self._field_values = dict(self._original_values)
        self._modified = False
        self._errors.clear()
    
    def ValidateField(self, field_name, value):
        """Validate field value"""
        field = self._field_info.get(field_name)
        if not field:
            return None
        
        if field.get('required') and not value:
            return "This field is required"
        
        if field.get('type') == 'number':
            try:
                float(value)
            except:
                return "Must be a valid number"
        
        if field.get('type') == 'integer':
            try:
                int(value)
            except:
                return "Must be a valid integer"
        
        return None
    
    def GetError(self, field_name):
        """Get validation error for field"""
        return self._errors.get(field_name)
    
    def __getitem__(self, key):
        """Support indexer for data binding"""
        return self.GetValue(key)
    
    def __setitem__(self, key, value):
        """Support indexer for data binding"""
        self.SetValue(key, value)


class ChangeCommand(object):
    """Base class for undoable commands"""
    
    def __init__(self, data_item, field_name, old_value, new_value):
        self.data_item = data_item
        self.field_name = field_name
        self.old_value = old_value
        self.new_value = new_value
    
    def Execute(self):
        """Execute the command"""
        self.data_item.SetValue(self.field_name, self.new_value)
    
    def Undo(self):
        """Undo the command"""
        self.data_item.SetValue(self.field_name, self.old_value)
    
    def GetDescription(self):
        """Get command description"""
        return "Change {} from '{}' to '{}'".format(
            self.field_name, 
            str(self.old_value)[:30] if self.old_value else "(empty)",
            str(self.new_value)[:30] if self.new_value else "(empty)"
        )


class BatchChangeCommand(object):
    """Command for batch changes"""
    
    def __init__(self, commands):
        self.commands = commands
    
    def Execute(self):
        """Execute all commands"""
        for cmd in self.commands:
            cmd.Execute()
    
    def Undo(self):
        """Undo all commands in reverse order"""
        for cmd in reversed(self.commands):
            cmd.Undo()
    
    def GetDescription(self):
        """Get batch description"""
        return "Batch change ({} items)".format(len(self.commands))


class UndoRedoManager(object):
    """Manages undo/redo operations"""
    
    def __init__(self, max_history=100):
        self.undo_stack = []
        self.redo_stack = []
        self.max_history = max_history
        self.on_state_changed = None
    
    def ExecuteCommand(self, command):
        """Execute command and add to undo stack"""
        command.Execute()
        self.undo_stack.append(command)
        
        # Clear redo stack on new action
        self.redo_stack = []
        
        # Limit history size
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
        
        self._notify_state_changed()
    
    def CanUndo(self):
        """Check if undo is available"""
        return len(self.undo_stack) > 0
    
    def CanRedo(self):
        """Check if redo is available"""
        return len(self.redo_stack) > 0
    
    def Undo(self):
        """Perform undo operation"""
        if not self.CanUndo():
            return False
        
        command = self.undo_stack.pop()
        command.Undo()
        self.redo_stack.append(command)
        
        self._notify_state_changed()
        return True
    
    def Redo(self):
        """Perform redo operation"""
        if not self.CanRedo():
            return False
        
        command = self.redo_stack.pop()
        command.Execute()
        self.undo_stack.append(command)
        
        self._notify_state_changed()
        return True
    
    def Clear(self):
        """Clear all history"""
        self.undo_stack = []
        self.redo_stack = []
        self._notify_state_changed()
    
    def GetUndoCount(self):
        """Get number of undo operations available"""
        return len(self.undo_stack)
    
    def GetRedoCount(self):
        """Get number of redo operations available"""
        return len(self.redo_stack)
    
    def GetLastUndoDescription(self):
        """Get description of last undo operation"""
        if self.undo_stack:
            return self.undo_stack[-1].GetDescription()
        return None
    
    def _notify_state_changed(self):
        """Notify listeners of state change"""
        if self.on_state_changed:
            self.on_state_changed()


class DataManager(object):
    """Main data management class"""
    
    def __init__(self):
        # Use object type for ObservableCollection in IronPython
        self.items = ObservableCollection[object]()
        self.undo_manager = UndoRedoManager()
        self.field_definitions = {}
        self.filter_predicate = None
    
    def LoadData(self, element_ids, field_info, data_matrix):
        """Load data into manager"""
        self.items.Clear()
        self.field_definitions = {f['name']: f for f in field_info if not f.get('hidden')}
        
        for i, elem_id in enumerate(element_ids):
            field_values = {}
            for j, field in enumerate(field_info):
                if not field.get('hidden'):
                    field_values[field['name']] = data_matrix[i][j]['value']
            
            item = DataItem(elem_id, field_values, self.field_definitions)
            self.items.Add(item)
    
    def GetModifiedItems(self):
        """Get all modified items"""
        modified = []
        for item in self.items:
            if item.IsModified:
                modified.append(item)
        return modified
    
    def GetModificationCount(self):
        """Get count of modifications"""
        count = 0
        for item in self.items:
            if item.IsModified:
                for field_name in self.field_definitions:
                    if item.GetValue(field_name) != item.GetOriginalValue(field_name):
                        count += 1
        return count
    
    def ApplyFilter(self, filter_func):
        """Apply filter to items"""
        self.filter_predicate = filter_func
    
    def ResetAllToOriginal(self):
        """Reset all items to original values"""
        commands = []
        for item in self.items:
            if item.IsModified:
                for field_name in self.field_definitions:
                    current = item.GetValue(field_name)
                    original = item.GetOriginalValue(field_name)
                    if current != original:
                        cmd = ChangeCommand(item, field_name, current, original)
                        commands.append(cmd)
        
        if commands:
            batch = BatchChangeCommand(commands)
            self.undo_manager.ExecuteCommand(batch)
    
    def FindAndReplace(self, find_text, replace_text, column_name=None, use_regex=False, case_sensitive=False):
        """Find and replace in data
        
        Args:
            find_text: Text to find
            replace_text: Text to replace with
            column_name: Specific column name, or None for all columns
            use_regex: Use regular expressions
            case_sensitive: Case sensitive search
        """
        import re
        
        commands = []
        
        for item in self.items:
            # Determine which fields to check
            if column_name and column_name != "All Columns":
                # Check only the specified column if it exists
                if column_name in self.field_definitions:
                    fields_to_check = [column_name]
                else:
                    continue  # Skip if column doesn't exist
            else:
                # Check all visible fields
                fields_to_check = list(self.field_definitions.keys())
            
            for field_name in fields_to_check:
                current_value = str(item.GetValue(field_name) or "")
                new_value = current_value
                
                if use_regex:
                    try:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        new_value = re.sub(find_text, replace_text, current_value, flags=flags)
                    except:
                        continue
                else:
                    if case_sensitive:
                        if find_text in current_value:
                            new_value = current_value.replace(find_text, replace_text)
                    else:
                        if find_text.lower() in current_value.lower():
                            # Case-insensitive replacement
                            pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                            new_value = pattern.sub(replace_text, current_value)
                
                if new_value != current_value:
                    cmd = ChangeCommand(item, field_name, current_value, new_value)
                    commands.append(cmd)
        
        if commands:
            batch = BatchChangeCommand(commands)
            self.undo_manager.ExecuteCommand(batch)
            return len(commands)
        
        return 0
    
    def FillEmpty(self, column_name, fill_value):
        """Fill empty cells in column"""
        commands = []
        
        for item in self.items:
            current_value = str(item.GetValue(column_name) or "").strip()
            if not current_value:
                cmd = ChangeCommand(item, column_name, current_value, fill_value)
                commands.append(cmd)
        
        if commands:
            batch = BatchChangeCommand(commands)
            self.undo_manager.ExecuteCommand(batch)
            return len(commands)
        
        return 0
    
    def FillColumn(self, column_name, fill_value):
        """Fill entire column with value"""
        commands = []
        
        for item in self.items:
            current_value = item.GetValue(column_name)
            if str(current_value) != str(fill_value):
                cmd = ChangeCommand(item, column_name, current_value, fill_value)
                commands.append(cmd)
        
        if commands:
            batch = BatchChangeCommand(commands)
            self.undo_manager.ExecuteCommand(batch)
            return len(commands)
        
        return 0
    
    def ExportToCSV(self, file_path):
        """Export data to CSV"""
        import csv
        
        try:
            with open(file_path, 'wb') as f:
                # UTF-8 BOM for Excel
                f.write('\xef\xbb\xbf')
                
                # Get visible fields
                visible_fields = [name for name, field in self.field_definitions.items()]
                
                # Write headers
                headers = ['ElementID'] + visible_fields
                writer = csv.writer(f)
                writer.writerow(headers)
                
                # Write data
                for item in self.items:
                    # Use ElementIdValue property for compatibility
                    row = [str(item.ElementIdValue)]
                    for field_name in visible_fields:
                        value = item.GetValue(field_name)
                        row.append(str(value) if value else "")
                    writer.writerow(row)
            
            return True, None
        except Exception as ex:
            return False, str(ex)
    
    def ImportFromCSV(self, file_path, element_id_map):
        """Import data from CSV"""
        import csv
        
        try:
            commands = []
            
            with open(file_path, 'rb') as f:
                # Skip BOM if present
                first_bytes = f.read(3)
                if first_bytes != '\xef\xbb\xbf':
                    f.seek(0)
                
                reader = csv.DictReader(f)
                
                for row in reader:
                    elem_id_str = row.get('ElementID', '')
                    if not elem_id_str:
                        continue
                    
                    # Find matching item using ElementIdValue
                    matching_item = None
                    for item in self.items:
                        if str(item.ElementIdValue) == elem_id_str:
                            matching_item = item
                            break
                    
                    if not matching_item:
                        continue
                    
                    # Update fields
                    for field_name, new_value in row.items():
                        if field_name == 'ElementID':
                            continue
                        
                        if field_name in self.field_definitions:
                            current_value = matching_item.GetValue(field_name)
                            if str(current_value) != str(new_value):
                                cmd = ChangeCommand(matching_item, field_name, current_value, new_value)
                                commands.append(cmd)
            
            if commands:
                batch = BatchChangeCommand(commands)
                self.undo_manager.ExecuteCommand(batch)
                return True, len(commands)
            
            return True, 0
            
        except Exception as ex:
            return False, str(ex)