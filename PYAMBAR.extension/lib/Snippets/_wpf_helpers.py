"""
Nome do arquivo: _wpf_helpers.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
Helpers para WPF em IronPython, incluindo implementação de INotifyPropertyChanged
para data binding e controles dinâmicos.

Autor: Thiago Barreto Sobral Nunes
Data: 22.10.2025
Versão: 1.0

Funções:
- PropertyChangedBase: Base class para INotifyPropertyChanged
- create_combo_from_xaml(options): Cria ComboBox usando XamlReader

Uso:
from Snippets import _wpf_helpers

class MyDataItem(_wpf_helpers.PropertyChangedBase):
    def __init__(self):
        _wpf_helpers.PropertyChangedBase.__init__(self)
        self._value = ""
    
    @property
    def Value(self):
        return self._value
    
    @Value.setter
    def Value(self, value):
        self._value = value
        self.OnPropertyChanged("Value")
"""

import clr
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')

from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs
from System.Windows.Markup import XamlReader
from System.IO import StringReader
from System.Xml import XmlReader


# ============================================================================
# PROPERTY CHANGED BASE CLASS
# ============================================================================

class PropertyChangedBase(object):
    """
    Base class para INotifyPropertyChanged implementation em IronPython.
    
    Permite que objetos notifiquem a UI quando propriedades mudam,
    essencial para data binding em WPF.
    
    Example:
        >>> class Person(PropertyChangedBase):
        ...     def __init__(self, name):
        ...         PropertyChangedBase.__init__(self)
        ...         self._name = name
        ...     
        ...     @property
        ...     def Name(self):
        ...         return self._name
        ...     
        ...     @Name.setter
        ...     def Name(self, value):
        ...         self._name = value
        ...         self.OnPropertyChanged("Name")
    """
    
    def __init__(self):
        self._property_changed_handlers = []
    
    def add_PropertyChanged(self, handler):
        """
        Subscribe to PropertyChanged event
        
        Args:
            handler: Event handler function
        """
        self._property_changed_handlers.append(handler)
    
    def remove_PropertyChanged(self, handler):
        """
        Unsubscribe from PropertyChanged event
        
        Args:
            handler: Event handler function
        """
        if handler in self._property_changed_handlers:
            self._property_changed_handlers.remove(handler)
    
    def OnPropertyChanged(self, property_name):
        """
        Raise PropertyChanged event para notificar UI
        
        Args:
            property_name (str): Nome da propriedade que mudou
        
        Example:
            >>> self._value = new_value
            >>> self.OnPropertyChanged("Value")
        """
        args = PropertyChangedEventArgs(property_name)
        for handler in self._property_changed_handlers:
            handler(self, args)
    
    PropertyChanged = property(lambda self: None, lambda self, value: None)


# ============================================================================
# COMBOBOX HELPERS
# ============================================================================

def create_combo_from_xaml(options=None):
    """
    Cria ComboBox usando XamlReader (solução para IronPython).
    
    Esta função resolve o problema "Cannot create instances of ComboBox 
    because it has no public constructors" no IronPython.
    
    Args:
        options (list): Lista de opções para preencher ComboBox
    
    Returns:
        ComboBox: Controle WPF ComboBox pronto para uso
        None: Em caso de erro
    
    Example:
        >>> combo = create_combo_from_xaml(['Option 1', 'Option 2', 'Option 3'])
        >>> combo.SelectedIndex = 0
        >>> panel.Children.Add(combo)
    """
    try:
        xaml = '<ComboBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Height="28"/>'
        
        string_reader = StringReader(xaml)
        xml_reader = XmlReader.Create(string_reader)
        combo = XamlReader.Load(xml_reader)
        
        # Adicionar items se fornecidos
        if options:
            for opt in options:
                combo.Items.Add(opt)
        
        return combo
        
    except Exception as e:
        print("Erro ao criar ComboBox: {}".format(str(e)))
        return None


def create_combo_factory(default_height=28, default_width=None):
    """
    Cria factory function para criar ComboBoxes com configurações padrão.
    
    Args:
        default_height (int): Altura padrão dos ComboBoxes
        default_width (int): Largura padrão dos ComboBoxes
    
    Returns:
        function: Factory function que cria ComboBoxes
    
    Example:
        >>> create_combo = create_combo_factory(height=30, width=150)
        >>> combo1 = create_combo(['A', 'B', 'C'])
        >>> combo2 = create_combo(['X', 'Y', 'Z'])
    """
    def factory(options=None):
        xaml = '<ComboBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"'
        if default_height:
            xaml += ' Height="{}"'.format(default_height)
        if default_width:
            xaml += ' Width="{}"'.format(default_width)
        xaml += '/>'
        
        try:
            string_reader = StringReader(xaml)
            xml_reader = XmlReader.Create(string_reader)
            combo = XamlReader.Load(xml_reader)
            
            if options:
                for opt in options:
                    combo.Items.Add(opt)
            
            return combo
        except Exception as e:
            print("Erro ao criar ComboBox: {}".format(str(e)))
            return None
    
    return factory


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
EXEMPLO 1 - PropertyChangedBase para Data Binding:
```python
from Snippets import _wpf_helpers
from System.Collections.ObjectModel import ObservableCollection

class Person(_wpf_helpers.PropertyChangedBase):
    def __init__(self, name, age):
        _wpf_helpers.PropertyChangedBase.__init__(self)
        self._name = name
        self._age = age
    
    @property
    def Name(self):
        return self._name
    
    @Name.setter
    def Name(self, value):
        self._name = value
        self.OnPropertyChanged("Name")
    
    @property
    def Age(self):
        return self._age
    
    @Age.setter
    def Age(self, value):
        self._age = value
        self.OnPropertyChanged("Age")

# Usar com ItemsControl
items = ObservableCollection[object]()
items.Add(Person("João", 30))
items.Add(Person("Maria", 25))
itemsControl.ItemsSource = items

# Mudanças nas propriedades atualizam UI automaticamente
items[0].Name = "João Silva"  # UI atualiza automaticamente
```

EXEMPLO 2 - Criar ComboBox Dinamicamente:
```python
from Snippets import _wpf_helpers

# Método simples
combo = _wpf_helpers.create_combo_from_xaml(['Option 1', 'Option 2'])
panel.Children.Add(combo)

# Método factory (para criar múltiplos combos)
create_combo = _wpf_helpers.create_combo_factory(height=30, width=150)
combo1 = create_combo(['A', 'B', 'C'])
combo2 = create_combo(['X', 'Y', 'Z'])
panel.Children.Add(combo1)
panel.Children.Add(combo2)
```

EXEMPLO 3 - PropertyChangedBase para Schedule Row Items:
```python
from Snippets import _wpf_helpers

class ScheduleRowItem(_wpf_helpers.PropertyChangedBase):
    def __init__(self, element_id, field_values):
        _wpf_helpers.PropertyChangedBase.__init__(self)
        self._element_id = element_id
        self._field_values = field_values
    
    def get_value(self, field_name):
        return self._field_values.get(field_name, "")
    
    def set_value(self, field_name, value):
        old_value = self._field_values.get(field_name)
        if old_value != value:
            self._field_values[field_name] = value
            self.OnPropertyChanged(field_name)
    
    def __getitem__(self, key):
        # Permite acesso dict-like: item["FieldName"]
        return self._field_values.get(key, "")
```
"""
