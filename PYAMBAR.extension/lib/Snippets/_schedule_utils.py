"""
Nome do arquivo: _schedule_utils.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
Utilitários para manipulação de Schedules no Revit, incluindo extração de dados,
busca e substituição, e operações em massa.

Autor: Thiago Barreto Sobral Nunes
Data: 22.10.2025
Versão: 1.0

Funções:
- get_all_schedules(doc): Obtém todos os schedules do documento
- extract_schedule_data(schedule): Extrai dados completos de um schedule
- find_and_replace_in_schedule(schedule, find, replace, column, case_sensitive): Busca/substitui
- get_schedule_field_names(schedule): Obtém nomes dos campos
- is_valid_element_id(element_id): Verifica validade do ElementId (Revit 2026 compatible)

Uso:
from Snippets import _schedule_utils

schedules = _schedule_utils.get_all_schedules(doc)
element_ids, fields, data = _schedule_utils.extract_schedule_data(schedules[0])
"""

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *


# ============================================================================
# ELEMENT ID HELPERS (Revit 2026 Compatible)
# ============================================================================

def is_valid_element_id(element_id):
    """
    Verifica se ElementId é válido (compatível com todas versões Revit).
    
    Args:
        element_id (ElementId): ElementId a verificar
    
    Returns:
        bool: True se válido, False caso contrário
    
    Example:
        >>> elem_id = element.Id
        >>> if is_valid_element_id(elem_id):
        ...     process_element(elem_id)
    """
    try:
        # Revit 2024+
        return element_id.Value != -1
    except AttributeError:
        try:
            # Revit 2023-
            return element_id.IntegerValue != -1
        except:
            try:
                return element_id != ElementId.InvalidElementId
            except:
                return False


def get_element_id_value(element_id):
    """
    Obtém valor inteiro do ElementId (compatível com Revit 2024+).
    
    Args:
        element_id (ElementId): ElementId
    
    Returns:
        int: Valor inteiro do ElementId
    
    Example:
        >>> elem_id = element.Id
        >>> id_value = get_element_id_value(elem_id)
        >>> print("Element ID: {}".format(id_value))
    """
    try:
        # Revit 2024+
        return element_id.Value
    except AttributeError:
        # Revit 2023-
        return element_id.IntegerValue


# ============================================================================
# SCHEDULE LISTING AND SELECTION
# ============================================================================

def get_all_schedules(doc):
    """
    Obtém todos os schedules válidos do documento.
    
    Args:
        doc (Document): Documento do Revit
    
    Returns:
        list: Lista de ViewSchedule ordenada por nome
        None: Em caso de erro
    
    Example:
        >>> schedules = get_all_schedules(doc)
        >>> for sched in schedules:
        ...     print(sched.Name)
    """
    try:
        schedules = []
        collector = FilteredElementCollector(doc).OfClass(ViewSchedule)
        
        for schedule in collector:
            # Filtrar schedules inválidos
            if not schedule.IsTitleblockRevisionSchedule and \
               schedule.Definition and \
               schedule.Definition.IsValidObject:
                schedules.append(schedule)
        
        return sorted(schedules, key=lambda s: s.Name)
    
    except Exception as e:
        print("Erro ao obter schedules: {}".format(str(e)))
        return None


def get_schedule_by_name(doc, schedule_name):
    """
    Obtém schedule por nome.
    
    Args:
        doc (Document): Documento do Revit
        schedule_name (str): Nome do schedule
    
    Returns:
        ViewSchedule: Schedule encontrado
        None: Se não encontrado ou erro
    
    Example:
        >>> sched = get_schedule_by_name(doc, "Door Schedule")
        >>> if sched:
        ...     print("Found: {}".format(sched.Name))
    """
    try:
        schedules = get_all_schedules(doc)
        if schedules:
            for sched in schedules:
                if sched.Name == schedule_name:
                    return sched
        return None
    except Exception as e:
        print("Erro ao buscar schedule: {}".format(str(e)))
        return None


# ============================================================================
# SCHEDULE FIELD OPERATIONS
# ============================================================================

def get_schedule_field_names(schedule):
    """
    Obtém nomes de todos os campos do schedule.
    
    Args:
        schedule (ViewSchedule): Schedule
    
    Returns:
        list: Lista com nomes dos campos
        None: Em caso de erro
    
    Example:
        >>> field_names = get_schedule_field_names(schedule)
        >>> print("Fields: {}".format(", ".join(field_names)))
    """
    try:
        field_names = []
        schedule_def = schedule.Definition
        
        for i in range(schedule_def.GetFieldCount()):
            field = schedule_def.GetField(i)
            if not field.IsHidden:
                field_names.append(field.GetName())
        
        return field_names
    
    except Exception as e:
        print("Erro ao obter campos: {}".format(str(e)))
        return None


def get_schedule_field_info(schedule):
    """
    Obtém informações detalhadas de todos os campos do schedule.
    
    Args:
        schedule (ViewSchedule): Schedule
    
    Returns:
        list: Lista de dicionários com info dos campos
        None: Em caso de erro
    
    Example:
        >>> fields = get_schedule_field_info(schedule)
        >>> for field in fields:
        ...     print("{}: can_edit={}".format(field['name'], field['can_edit']))
    """
    try:
        fields_info = []
        schedule_def = schedule.Definition
        
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
                    'is_calculated': field.IsCalculatedField
                })
            except:
                fields_info.append({
                    'index': i,
                    'name': field.GetName(),
                    'schedulable': None,
                    'hidden': field.IsHidden,
                    'can_edit': False,
                    'is_calculated': True
                })
        
        return fields_info
    
    except Exception as e:
        print("Erro ao obter info dos campos: {}".format(str(e)))
        return None


# ============================================================================
# SCHEDULE DATA EXTRACTION
# ============================================================================

def extract_schedule_data(schedule):
    """
    Extrai dados completos de um schedule (elementos, campos e valores).
    
    Args:
        schedule (ViewSchedule): Schedule para extrair dados
    
    Returns:
        tuple: (element_ids, fields_info, data_matrix)
            - element_ids: Lista de ElementIds
            - fields_info: Informações dos campos
            - data_matrix: Matriz com valores e parâmetros
        None: Em caso de erro
    
    Example:
        >>> elem_ids, fields, data = extract_schedule_data(schedule)
        >>> print("Loaded {} elements with {} fields".format(
        ...     len(elem_ids), len(fields)
        ... ))
    """
    try:
        doc = schedule.Document
        schedule_def = schedule.Definition
        
        # Obter informações dos campos
        fields_info = get_schedule_field_info(schedule)
        if not fields_info:
            return None
        
        # Obter elementos no schedule
        collector = FilteredElementCollector(doc, schedule.Id)
        element_ids = list(collector.ToElementIds())
        
        # Construir matriz de dados
        data_matrix = []
        
        for elem_id in element_ids:
            element = doc.GetElement(elem_id)
            if not element:
                continue
            
            row_data = []
            
            for field_info in fields_info:
                if field_info['schedulable']:
                    param = _get_parameter(doc, element, field_info['schedulable'])
                    value = _get_param_value(doc, param) if param else ""
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
                    # Campo calculado
                    row_data.append({
                        'value': field_info.get('name', ''),
                        'param': None,
                        'storage_type': None,
                        'readonly': True,
                        'element': element
                    })
            
            data_matrix.append(row_data)
        
        return element_ids, fields_info, data_matrix
    
    except Exception as e:
        print("Erro ao extrair dados: {}".format(str(e)))
        import traceback
        print(traceback.format_exc())
        return None


def _get_parameter(doc, element, schedulable_field):
    """
    Obtém parâmetro do elemento baseado no schedulable field (interno).
    
    Args:
        doc (Document): Documento
        element (Element): Elemento
        schedulable_field: Campo schedulable
    
    Returns:
        Parameter: Parâmetro encontrado ou None
    """
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


def _get_param_value(doc, param):
    """
    Extrai valor do parâmetro como string (interno, Revit 2026 compatible).
    
    Args:
        doc (Document): Documento
        param (Parameter): Parâmetro
    
    Returns:
        str: Valor como string ou "" se vazio
    """
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


# ============================================================================
# FIND AND REPLACE
# ============================================================================

def find_and_replace_in_schedule(schedule, find_text, replace_text, 
                                  column_name=None, case_sensitive=False):
    """
    Busca e substitui texto em um schedule (sem aplicar no Revit).
    
    Args:
        schedule (ViewSchedule): Schedule
        find_text (str): Texto a buscar
        replace_text (str): Texto para substituir
        column_name (str): Nome da coluna (None = todas colunas)
        case_sensitive (bool): Busca case-sensitive
    
    Returns:
        int: Número de ocorrências substituídas
        None: Em caso de erro
    
    Example:
        >>> count = find_and_replace_in_schedule(
        ...     schedule, "old", "new", "Comments", False
        ... )
        >>> print("Replaced {} occurrences".format(count))
    """
    try:
        import re
        
        # Extrair dados
        result = extract_schedule_data(schedule)
        if not result:
            return 0
        
        element_ids, fields_info, data_matrix = result
        count = 0
        
        # Determinar quais campos processar
        target_fields = []
        if column_name:
            for field in fields_info:
                if field['name'] == column_name and not field['hidden']:
                    target_fields.append(field)
        else:
            target_fields = [f for f in fields_info if not f['hidden']]
        
        # Processar cada linha
        for row_data in data_matrix:
            for field_info in target_fields:
                field_index = field_info['index']
                cell_data = row_data[field_index]
                
                if cell_data['readonly'] or not cell_data['param']:
                    continue
                
                current_value = cell_data['value']
                
                if not current_value:
                    continue
                
                # Realizar substituição
                if case_sensitive:
                    new_value = current_value.replace(find_text, replace_text)
                else:
                    pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                    new_value = pattern.sub(replace_text, current_value)
                
                if new_value != current_value:
                    # Nota: Esta função apenas retorna o count
                    # Aplicação real requer Transaction
                    count += 1
        
        return count
    
    except Exception as e:
        print("Erro em find_and_replace: {}".format(str(e)))
        return None


# ============================================================================
# SCHEDULE STATISTICS
# ============================================================================

def get_schedule_stats(schedule):
    """
    Obtém estatísticas do schedule.
    
    Args:
        schedule (ViewSchedule): Schedule
    
    Returns:
        dict: Dicionário com estatísticas
        None: Em caso de erro
    
    Example:
        >>> stats = get_schedule_stats(schedule)
        >>> print("Elements: {}".format(stats['element_count']))
        >>> print("Fields: {}".format(stats['field_count']))
    """
    try:
        doc = schedule.Document
        schedule_def = schedule.Definition
        
        # Contar campos
        total_fields = schedule_def.GetFieldCount()
        visible_fields = 0
        calculated_fields = 0
        
        for i in range(total_fields):
            field = schedule_def.GetField(i)
            if not field.IsHidden:
                visible_fields += 1
            if field.IsCalculatedField:
                calculated_fields += 1
        
        # Contar elementos
        collector = FilteredElementCollector(doc, schedule.Id)
        element_count = collector.GetElementCount()
        
        return {
            'name': schedule.Name,
            'element_count': element_count,
            'total_fields': total_fields,
            'visible_fields': visible_fields,
            'hidden_fields': total_fields - visible_fields,
            'calculated_fields': calculated_fields,
            'editable_fields': visible_fields - calculated_fields
        }
    
    except Exception as e:
        print("Erro ao obter stats: {}".format(str(e)))
        return None


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
EXEMPLO 1 - Listar todos os schedules:
```python
from Snippets import _schedule_utils

schedules = _schedule_utils.get_all_schedules(doc)
print("Schedules encontrados: {}".format(len(schedules)))

for sched in schedules:
    stats = _schedule_utils.get_schedule_stats(sched)
    print("{}: {} elementos, {} campos".format(
        stats['name'], 
        stats['element_count'], 
        stats['visible_fields']
    ))
```

EXEMPLO 2 - Extrair dados de um schedule:
```python
from Snippets import _schedule_utils

# Obter schedule por nome
schedule = _schedule_utils.get_schedule_by_name(doc, "Door Schedule")

if schedule:
    # Extrair dados
    elem_ids, fields, data = _schedule_utils.extract_schedule_data(schedule)
    
    print("Carregados {} elementos".format(len(elem_ids)))
    print("Campos: {}".format([f['name'] for f in fields if not f['hidden']]))
    
    # Acessar dados
    for i, elem_id in enumerate(elem_ids):
        row = data[i]
        for j, field in enumerate(fields):
            if not field['hidden']:
                cell = row[j]
                print("{}: {}".format(field['name'], cell['value']))
```

EXEMPLO 3 - Buscar e substituir (com Transaction):
```python
from Snippets import _schedule_utils
from Autodesk.Revit.DB import Transaction

schedule = _schedule_utils.get_schedule_by_name(doc, "Room Schedule")

if schedule:
    # Primeiro, verificar quantas ocorrências
    count = _schedule_utils.find_and_replace_in_schedule(
        schedule, "old text", "new text", "Comments", False
    )
    
    print("Encontradas {} ocorrências".format(count))
    
    # Para aplicar no Revit, precisa de Transaction e código adicional
    # (veja RevitSheet Pro script.py para implementação completa)
```

EXEMPLO 4 - Obter campos editáveis:
```python
from Snippets import _schedule_utils

fields = _schedule_utils.get_schedule_field_info(schedule)

editable_fields = [f for f in fields if f['can_edit'] and not f['hidden']]
readonly_fields = [f for f in fields if not f['can_edit'] and not f['hidden']]

print("Campos editáveis: {}".format([f['name'] for f in editable_fields]))
print("Campos somente leitura: {}".format([f['name'] for f in readonly_fields]))
```

EXEMPLO 5 - Verificar ElementId:
```python
from Snippets import _schedule_utils

for elem_id in element_ids:
    if _schedule_utils.is_valid_element_id(elem_id):
        id_value = _schedule_utils.get_element_id_value(elem_id)
        element = doc.GetElement(elem_id)
        print("Element {}: {}".format(id_value, element.Name))
```
"""
