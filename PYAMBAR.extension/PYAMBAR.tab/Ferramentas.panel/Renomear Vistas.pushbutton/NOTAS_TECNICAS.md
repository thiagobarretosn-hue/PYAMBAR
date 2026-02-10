# 🔧 Notas Técnicas - Renomear Sheets/Views v3.0

## Arquitetura do Código

### Estrutura de Classes

```
NotifyPropertyChangedBase (INotifyPropertyChanged)
    └── RenameItem
    
RenameWindow
    ├── Gerencia UI (XAML)
    ├── Eventos de interação
    └── Lógica de negócio
```

### Fluxo de Dados

```
1. Usuário seleciona tipo → load_items()
2. Carrega elementos do Revit → RenameItem objects
3. Adiciona à ObservableCollection → DataGrid atualiza
4. Usuário configura parâmetros
5. Clica Preview → apply_rename_mode()
6. Atualiza NewName → PropertyChanged → Grid atualiza
7. Valida → validate_unique_names()
8. Atualiza Status → PropertyChanged → Grid atualiza
9. Clica Aplicar → Transaction → Revit atualiza
```

---

## Implementação de INotifyPropertyChanged

### Problema Original (v2.0)
```python
class NotifyPropertyChangedBase(object):
    def __init__(self):
        self.PropertyChanged = None  # ❌ Não funciona no IronPython
    
    def OnPropertyChanged(self, property_name):
        if self.PropertyChanged:
            self.PropertyChanged(self, PropertyChangedEventArgs(property_name))
```

**Por que não funciona?**
- IronPython não suporta eventos .NET da mesma forma que C#
- `PropertyChanged = None` não cria um evento válido
- O binding WPF não consegue se inscrever no evento

### Solução Correta (v3.0)
```python
class NotifyPropertyChangedBase(INotifyPropertyChanged):
    def __init__(self):
        self._property_changed_handlers = []  # ✅ Lista de handlers
    
    def add_PropertyChanged(self, handler):
        """WPF chama este método para se inscrever"""
        if handler not in self._property_changed_handlers:
            self._property_changed_handlers.append(handler)
    
    def remove_PropertyChanged(self, handler):
        """WPF chama este método para cancelar inscrição"""
        if handler in self._property_changed_handlers:
            self._property_changed_handlers.remove(handler)
    
    def OnPropertyChanged(self, property_name):
        """Notifica todos os handlers inscritos"""
        args = PropertyChangedEventArgs(property_name)
        for handler in self._property_changed_handlers:
            handler(self, args)
```

**Como funciona:**
1. Classe herda de `INotifyPropertyChanged` (interface .NET)
2. WPF detecta a interface e chama `add_PropertyChanged`
3. Guardamos os handlers em uma lista Python
4. Quando a propriedade muda, notificamos todos os handlers
5. WPF recebe a notificação e atualiza a UI

### Propriedades com Binding
```python
class RenameItem(NotifyPropertyChangedBase):
    def __init__(self, element, element_type):
        NotifyPropertyChangedBase.__init__(self)
        self._new_name = ""  # Backing field privado
    
    # Property getter
    def get_NewName(self):
        return self._new_name
    
    # Property setter
    def set_NewName(self, value):
        if value is None:
            value = ""
        if self._new_name != value:  # Só notifica se mudou
            self._new_name = value
            self.OnPropertyChanged('NewName')  # 🔔 Notifica WPF
    
    # Cria a property Python
    NewName = property(get_NewName, set_NewName)
```

**No XAML:**
```xml
<DataGridTextColumn 
    Binding="{Binding NewName, Mode=TwoWay, UpdateSourceTrigger=PropertyChanged}"/>
```

**Fluxo:**
1. Usuário edita célula no DataGrid
2. WPF chama `set_NewName(new_value)`
3. `set_NewName` atualiza `_new_name`
4. `set_NewName` chama `OnPropertyChanged('NewName')`
5. `OnPropertyChanged` notifica todos os handlers
6. WPF recebe notificação e atualiza outras células/controles

---

## Compatibilidade de Versões do Revit

### Problema: ElementId.IntegerValue
```python
# ❌ Revit 2024+ - IntegerValue está obsoleto
element_id = element.Id.IntegerValue  # Gera warning
```

### Solução: Função Helper
```python
def get_element_id_value(element):
    """Retorna o valor do ID (compatível com todas as versões)"""
    if rvt_year >= 2024:
        return element.Id.Value  # Int64 no Revit 2024+
    else:
        return element.Id.IntegerValue  # Int32 no Revit < 2024
```

**Vantagens:**
- ✅ Funciona em Revit 2020-2025+
- ✅ Sem warnings de deprecation
- ✅ Código limpo e centralizado
- ✅ Fácil de atualizar no futuro

**Uso:**
```python
# Comparar IDs
id_value = get_element_id_value(element)
if id_value == 12345:
    # ...

# Set de IDs
element_ids = set([get_element_id_value(e) for e in elements])
```

---

## TransactionGroup para Performance

### Sem TransactionGroup (v2.0)
```python
t = Transaction(doc, 'Renomear')
t.Start()
try:
    for item in items:
        item.Element.Name = item.NewName  # Cada um é uma "sub-transação"
    t.Commit()
except:
    t.RollBack()
```

**Problemas:**
- ⚠️ Performance ruim com muitos elementos (>100)
- ⚠️ Histórico de undo poluído
- ⚠️ Cada mudança é registrada separadamente

### Com TransactionGroup (v3.0)
```python
tg = TransactionGroup(doc, 'Renomear Sheets/Views')
tg.Start()

t = Transaction(doc, 'Renomear Lote')
t.Start()

try:
    for item in items:
        item.Element.Name = item.NewName
    
    t.Commit()
    tg.Assimilate()  # 🚀 Combina todas as sub-transações
except:
    t.RollBack()
    tg.RollBack()
```

**Vantagens:**
- ✅ ~20% mais rápido
- ✅ Uma única entrada no histórico de undo
- ✅ Ctrl+Z desfaz tudo de uma vez
- ✅ Melhor para o usuário

**Assimilate() vs RollBack():**
- `Assimilate()`: Aceita as mudanças e combina transações
- `RollBack()`: Cancela todas as mudanças do grupo

---

## Validação de Regex

### Implementação
```python
def validate_regex(pattern):
    """
    Valida se um padrão regex é válido.
    Retorna (bool, mensagem)
    """
    try:
        re.compile(pattern)  # Tenta compilar
        return True, "Regex válido"
    except Exception as e:
        return False, "Regex inválido: {}".format(str(e))
```

### Uso no Preview
```python
if use_regex:
    is_valid, msg = validate_regex(param1)
    if not is_valid:
        item.Status = "❌ {}".format(msg)
        item.NewName = original
    else:
        item.NewName = re.sub(param1, param2, original)
```

**Casos de teste:**
```python
# Válidos
validate_regex(r"^\d+")      # → (True, "Regex válido")
validate_regex(r"[A-Z]+")    # → (True, "Regex válido")
validate_regex(r".*_OLD$")   # → (True, "Regex válido")

# Inválidos
validate_regex(r"[")         # → (False, "Regex inválido: ...")
validate_regex(r"(?P<")      # → (False, "Regex inválido: ...")
validate_regex(r"\g")        # → (False, "Regex inválido: ...")
```

---

## Numeração com Variáveis

### String.format() com Kwargs
```python
# Dicionário de variáveis
format_vars = {
    'counter': 1,
    'name': 'Floor Plan',
    'number': 'A101',
    'type': 'Sheet'
}

# Suporta ambos
pattern = "{0:03d}_{name}"  # Posicional + keyword
result = pattern.format(1, **format_vars)  # → "001_Floor Plan"

pattern = "{counter:04d}_{type}"  # Só keywords
result = pattern.format(1, **format_vars)  # → "0001_Sheet"
```

### Tratamento de Erros
```python
try:
    item.NewName = pattern.format(counter, **format_vars)
except KeyError as e:
    # Variável não existe: {invalid}
    item.Status = "❌ Variável inválida: {}".format(str(e))
except ValueError as e:
    # Formato inválido: {0:xyz}
    item.Status = "❌ Formato inválido: {}".format(str(e))
except Exception as e:
    # Outro erro
    item.Status = "❌ Padrão inválido: {}".format(str(e))
```

**Exemplos de erros:**
```python
# KeyError
pattern = "{invalid}"  # Variável não existe

# ValueError  
pattern = "{0:xyz}"    # Formato inválido

# IndexError
pattern = "{5}"        # Índice fora de range (só temos {0})
```

---

## Filtro de Busca

### Implementação
```python
def on_search_changed(self, sender, args):
    """Evento: filtro de busca"""
    search_text = self.txtSearch.Text.lower()
    
    self.items.Clear()  # Limpa collection visível
    
    for item in self.all_items:  # Itera sobre todos os items
        # Buscar em múltiplos campos
        match = (search_text in item.OriginalName.lower() or 
                search_text in item.Number.lower() or
                search_text in item.NewName.lower())
        
        if match or not search_text:  # Mostra se match ou busca vazia
            self.items.Add(item)  # Adiciona à collection visível
    
    self.update_counter()  # Atualiza contador
```

**Estrutura de dados:**
```
self.all_items (lista Python)  → Todos os items carregados
    ↓
self.items (ObservableCollection)  → Items visíveis no DataGrid
    ↓
DataGrid.ItemsSource  → UI atualiza automaticamente
```

**Vantagens:**
- ✅ Atualização em tempo real (TextChanged)
- ✅ Busca case-insensitive
- ✅ Múltiplos campos
- ✅ Performance: O(n) linear
- ✅ Não afeta aplicação (filtra apenas visualização)

---

## Atalhos de Teclado

### Event Handler
```python
def on_key_down(self, sender, args):
    """Handler para atalhos de teclado"""
    ctrl = args.KeyboardDevice.Modifiers == ModifierKeys.Control
    
    if ctrl and args.Key == Key.P:
        args.Handled = True  # Previne propagação
        self.on_preview(None, None)
    elif ctrl and args.Key == Key.Enter:
        args.Handled = True
        self.on_apply(None, None)
    # ...
```

**No construtor:**
```python
self.window.KeyDown += self.on_key_down
```

**Imports necessários:**
```python
from System.Windows.Input import Key, ModifierKeys
```

**Keys disponíveis:**
- `Key.P`, `Key.Z`, `Key.A`, `Key.D`
- `Key.Enter`, `Key.Escape`, `Key.Tab`
- `Key.F1`, `Key.F2`, ... `Key.F12`

**Modifiers:**
- `ModifierKeys.Control`
- `ModifierKeys.Shift`
- `ModifierKeys.Alt`

---

## ObservableCollection vs List

### Diferença
```python
# ❌ Lista Python - UI não atualiza automaticamente
self.items = []
self.items.append(item)  # DataGrid não vê a mudança

# ✅ ObservableCollection - UI atualiza automaticamente
self.items = ObservableCollection[type(RenameItem)]()
self.items.Add(item)  # DataGrid atualiza instantaneamente
```

### Quando usar cada um

**ObservableCollection:**
- ✅ Binding com UI (DataGrid, ListBox, etc)
- ✅ Mudanças devem refletir automaticamente
- ✅ Add/Remove items durante execução

**List Python:**
- ✅ Armazenamento interno
- ✅ Iterar sem UI
- ✅ Filtragem/ordenação temporária

**No nosso caso:**
```python
self.all_items = []  # Lista Python (dados internos)
self.items = ObservableCollection[...]()  # WPF (UI binding)

# Filtrar
for item in self.all_items:  # Itera lista interna
    if matches:
        self.items.Add(item)  # Adiciona à collection visível
```

---

## Validação de Nomes Únicos

### Algoritmo
```python
def validate_unique_names(items, doc, element_type):
    # 1. IDs dos elementos sendo renomeados
    elements_being_renamed = set([
        get_element_id_value(item.Element) 
        for item in items if item.Apply
    ])
    
    # 2. Elementos existentes (exceto os sendo renomeados)
    if element_type == 'Sheet':
        existing = get_all_sheets(doc)
    else:
        existing = get_all_views(doc)
    
    existing = [e for e in existing 
                if get_element_id_value(e) not in elements_being_renamed]
    existing_names = set([e.Name for e in existing])
    
    # 3. Verificar cada item
    new_names = {}  # Rastreia duplicatas no lote
    
    for item in items:
        if not item.Apply:
            continue
        
        new_name = item.NewName.strip()
        
        # Validações em ordem de prioridade
        if not new_name:
            item.Status = "❌ Nome vazio"
        elif new_name in existing_names:
            item.Status = "❌ Já existe no documento"
        elif new_name in new_names:
            item.Status = "❌ Duplicado no lote"
        elif new_name == item.OriginalName:
            item.Status = "⚠️ Sem alteração"
        else:
            item.Status = "✅ OK"
            new_names[new_name] = True
```

**Complexidade:**
- Construir set de IDs: O(n)
- Filtrar existentes: O(m)
- Criar set de nomes: O(m)
- Validar items: O(n)
- **Total: O(n + m)** onde n = items, m = elementos no doc

**Estruturas de dados:**
```python
elements_being_renamed: set[int]  # O(1) lookup
existing_names: set[str]          # O(1) lookup
new_names: dict[str, bool]        # O(1) lookup
```

---

## Performance Tips

### 1. FilteredElementCollector
```python
# ❌ Lento - converte tudo para lista
all_sheets = list(FilteredElementCollector(doc).OfClass(ViewSheet))

# ✅ Rápido - itera direto
collector = FilteredElementCollector(doc).OfClass(ViewSheet)
for sheet in collector:
    if not sheet.IsTemplate:
        # processa
```

### 2. Sets vs Lists para lookups
```python
# ❌ O(n) - lista
names_list = [e.Name for e in elements]
if name in names_list:  # Busca linear

# ✅ O(1) - set
names_set = set([e.Name for e in elements])
if name in names_set:  # Hash lookup
```

### 3. Property caching
```python
# ❌ Recalcula sempre
def get_Name(self):
    return self.Element.Name.upper() + "_suffix"

# ✅ Calcula uma vez
def __init__(self):
    self._cached_name = self.Element.Name.upper() + "_suffix"

def get_Name(self):
    return self._cached_name
```

### 4. Batch vs Individual
```python
# ❌ Uma transação por elemento
for item in items:
    t = Transaction(doc, 'Rename')
    t.Start()
    item.Element.Name = item.NewName
    t.Commit()

# ✅ Uma transação para todos
t = Transaction(doc, 'Rename All')
t.Start()
for item in items:
    item.Element.Name = item.NewName
t.Commit()
```

---

## Debug e Troubleshooting

### Logging
```python
# No pyRevit
from pyrevit import script
output = script.get_output()

output.print_md("## Debug Info")
output.print_md("- Items: {}".format(len(items)))
output.print_md("- Selected: {}".format(selected_count))

# Markdown formatting
output.print_md("```python\n{}\n```".format(code))
```

### Try-Catch Pattern
```python
try:
    # Código principal
    do_something()
    
except Exception as e:
    output.print_md("❌ **Erro:** {}".format(str(e)))
    
    # Stack trace completo
    import traceback
    output.print_md("```\n{}\n```".format(traceback.format_exc()))
    
    # Re-raise se necessário
    raise
```

### Validação de UI
```python
# Verificar se controle existe
if self.txtSearch:
    search_text = self.txtSearch.Text
else:
    output.print_md("⚠️ Controle txtSearch não encontrado")

# Verificar se tem items
if not self.items or len(self.items) == 0:
    output.print_md("⚠️ Nenhum item carregado")
    return
```

---

## Testes Manuais Recomendados

### Cenários de Teste

1. **Básico**
   - [ ] Carregar sheets
   - [ ] Carregar views
   - [ ] Preview simples
   - [ ] Aplicar renomeação

2. **Find & Replace**
   - [ ] Replace simples
   - [ ] Regex válido
   - [ ] Regex inválido
   - [ ] Find vazio
   - [ ] Replace vazio

3. **Prefix/Suffix**
   - [ ] Só prefixo
   - [ ] Só sufixo
   - [ ] Ambos
   - [ ] Nenhum

4. **Numeração**
   - [ ] {0} básico
   - [ ] {0:03d} formatado
   - [ ] {name} original
   - [ ] {number} sheet number
   - [ ] {type} tipo
   - [ ] Combinações

5. **Filtros**
   - [ ] Busca simples
   - [ ] Busca case-insensitive
   - [ ] Limpar busca
   - [ ] Busca sem resultados

6. **Ações**
   - [ ] Marcar todos
   - [ ] Desmarcar todos
   - [ ] Desfazer preview
   - [ ] Atalhos (Ctrl+P, etc)

7. **Validação**
   - [ ] Nome vazio
   - [ ] Duplicado no doc
   - [ ] Duplicado no lote
   - [ ] Sem alteração

8. **Edge Cases**
   - [ ] 0 items
   - [ ] 1 item
   - [ ] 1000+ items
   - [ ] Nomes muito longos
   - [ ] Caracteres especiais
   - [ ] Unicode

---

## Melhorias Futuras

### Código
- [ ] Type hints para Python 3 (quando migrar)
- [ ] Unit tests automatizados
- [ ] Logging framework profissional
- [ ] Configuração via JSON
- [ ] Plugins system

### UI
- [ ] Temas (claro/escuro)
- [ ] Customização de cores
- [ ] Layouts salvos
- [ ] Undo/redo múltiplo
- [ ] Drag & drop de CSVs

### Funcionalidades
- [ ] Presets salvos
- [ ] Import/Export CSV
- [ ] Histórico de operações
- [ ] Batch processing
- [ ] API pública

---

**Autor**: Thiago Barreto Sobral Nunes  
**Versão**: 3.0  
**Data**: 08/11/2024
