# -*- coding: utf-8 -*-
__title__ = "RevitSheet\nPro"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.0"
__doc__ = """
RevitSheet Pro v4.0 - Editor de schedules com DataGrid.
Atalhos: Ctrl+Z Undo, Ctrl+Y Redo, Ctrl+F Find, Ctrl+S Export CSV, Delete Clear
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

from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from System.Windows import *
from System.Windows.Controls import *
from System.Windows.Data import *
from System.Windows.Input import *
from System.Windows.Media import *
from System.Windows.Controls.Primitives import DataGridColumnHeader
from System.Collections.Generic import List
from System.Collections import IComparer
from System import Action, Predicate
from System.ComponentModel import ListSortDirection

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
        except Exception as e:
            try:
                return element_id != ElementId.InvalidElementId
            except Exception as e:
                return False


# ==================== SORT COMPARER ====================

def _sort_key(raw_value):
    """Chave de ordenacao natural: numeros comparam como numero, nao como texto.

    Sem isso "10" viria antes de "9". Retorna (grupo, num, texto) para que
    vazios fiquem sempre no fim e numeros antes de texto.
    """
    text = str(raw_value or "").strip()

    if not text:
        return (2, 0.0, "")  # vazios por ultimo

    try:
        return (0, float(text.replace(",", ".")), "")
    except (ValueError, AttributeError):
        return (1, 0.0, text.lower())


class ScheduleItemComparer(IComparer):
    """IComparer para ListCollectionView.CustomSort.

    Necessario porque o binding das colunas e um indexer ("[Campo]"), e
    SortDescriptions so resolve propriedades nomeadas via TypeDescriptor.
    """

    def __init__(self, field_name, ascending):
        self._field_name = field_name
        self._ascending = ascending

    def Compare(self, x, y):
        try:
            key_x = _sort_key(x.GetValue(self._field_name))
            key_y = _sort_key(y.GetValue(self._field_name))
        except Exception:
            return 0

        if key_x < key_y:
            result = -1
        elif key_x > key_y:
            result = 1
        else:
            result = 0

        return result if self._ascending else -result


# ==================== FIND/REPLACE DIALOG ====================

class FindReplaceDialog(forms.WPFWindow):
    """Custom Find and Replace dialog with column selection and match count"""

    def __init__(self, columns, data_manager=None):
        """Initialize dialog with available columns"""
        self.columns = columns
        self._data_manager = data_manager
        self.find_text = ""
        self.replace_text = ""
        self.selected_column = "All Columns"
        self.case_sensitive = False
        self.use_regex = False
        self.dialog_result = False

        # Load XAML from file
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
        self.btnCount.Click += self.on_count_click

        # Focus on find textbox
        self.txtFind.Focus()

    def _collect_params(self):
        """Collect current dialog parameters"""
        self.find_text = self.txtFind.Text.strip()
        self.replace_text = self.txtReplace.Text
        self.selected_column = str(self.cmbColumn.SelectedItem)
        self.case_sensitive = bool(self.chkCaseSensitive.IsChecked)
        self.use_regex = bool(self.chkUseRegex.IsChecked)

    def on_count_click(self, sender, e):
        """Count matches without replacing"""
        self._collect_params()
        if not self.find_text:
            self.txtMatchCount.Text = "Digite texto para buscar."
            return

        if not self._data_manager:
            self.txtMatchCount.Text = "(contagem indisponivel)"
            return

        import re
        count = 0
        col_name = None if self.selected_column == "All Columns" else self.selected_column

        for item in self._data_manager.items:
            if col_name:
                fields = [col_name] if col_name in self._data_manager.field_definitions else []
            else:
                fields = list(self._data_manager.field_definitions.keys())

            for field_name in fields:
                val = str(item.GetValue(field_name) or "")
                if self.use_regex:
                    try:
                        flags = 0 if self.case_sensitive else re.IGNORECASE
                        if re.search(self.find_text, val, flags):
                            count += 1
                    except Exception as e:
                        self.txtMatchCount.Text = "Regex invalida."
                        return
                else:
                    if self.case_sensitive:
                        if self.find_text in val:
                            count += 1
                    else:
                        if self.find_text.lower() in val.lower():
                            count += 1

        self.txtMatchCount.Text = "{} correspondencia(s) encontrada(s).".format(count)

    def on_replace_click(self, sender, e):
        """Handle Replace button click"""
        self._collect_params()

        if not self.find_text:
            self.txtMatchCount.Text = "Digite texto para buscar."
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
        """Get all valid schedules from document.

        Exclui view templates: eles aparecem como ViewSchedule mas quebram o
        FilteredElementCollector ("viewId is not valid for element iteration").
        """
        schedules = []
        collector = FilteredElementCollector(doc).OfClass(ViewSchedule)

        for schedule in collector:
            if schedule.IsTitleblockRevisionSchedule:
                continue
            if schedule.IsTemplate:
                continue
            if not schedule.Definition or not schedule.Definition.IsValidObject:
                continue
            schedules.append(schedule)

        return sorted(schedules, key=lambda s: s.Name)
    
    @staticmethod
    def _read_rendered_table_body(schedule, col_count, element_count):
        """Le a tabela COMO O REVIT RENDERIZA (texto das celulas).

        Necessario para campos calculados (Count/Contagem, formulas) e para
        parametros somente-leitura cujo valor nao sai via LookupParameter:
        eles nao existem como parametro em elemento nenhum.

        O numero de linhas de cabecalho dentro do Body varia conforme o
        schedule (ShowHeaders, titulo, cabecalho de grupo). Em vez de assumir
        que e sempre 1, o offset e CALIBRADO: descartamos do topo exatamente a
        diferenca entre as linhas do Body e a contagem de elementos.

        Se depois disso as linhas nao baterem 1:1 com os elementos, devolve
        vazio: celula em branco e melhor que celula com o valor de outra linha.
        """
        if element_count <= 0:
            return []

        try:
            section = schedule.GetTableData().GetSectionData(SectionType.Body)
            row_count = section.NumberOfRows
            max_cols = min(section.NumberOfColumns, col_count)

            offset = row_count - element_count

            # offset negativo = menos linhas que elementos (agrupado/consolidado)
            # offset grande = linhas de grupo intercaladas, nao so no topo.
            # Nos dois casos o alinhamento por posicao nao e confiavel.
            if offset < 0 or offset > 4:
                return []

            rows = []
            for r in range(offset, row_count):
                row = []
                for c in range(max_cols):
                    try:
                        row.append(schedule.GetCellText(SectionType.Body, r, c) or "")
                    except Exception:
                        row.append("")
                rows.append(row)

            if len(rows) != element_count:
                return []

            return rows
        except Exception:
            return []

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
            except Exception as e:
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

        # Remover RevitLinkInstance: quando o schedule tem IncludeLinkedFiles,
        # o collector do host devolve os proprios vinculos junto. Eles nao sao
        # elementos agendados — virariam linhas com todas as colunas vazias.
        # Se sobrar nada, o schedule e realmente de vinculos: nao filtrar.
        sem_links = [eid for eid in element_ids
                     if not isinstance(doc.GetElement(eid), RevitLinkInstance)]
        if sem_links:
            element_ids = sem_links

        # Indice da coluna VISIVEL de cada campo (a tabela renderizada so
        # contem colunas visiveis)
        visible_col_index = {}
        visible_count = 0
        for i, field_info in enumerate(fields_info):
            if not field_info['hidden']:
                visible_col_index[i] = visible_count
                visible_count += 1

        rendered_rows = ScheduleDataExtractor._read_rendered_table_body(
            schedule, visible_count, len(element_ids))

        # Um campo so e editavel se existir parametro GRAVAVEL por tras dele.
        # Nao dá para confiar em IsCalculatedField: campos como Contagem/Count
        # reportam IsCalculatedField=False mas nao tem parametro nenhum.
        field_has_editable_param = [False] * len(fields_info)

        # Build data matrix
        data_matrix = []
        for row_idx, elem_id in enumerate(element_ids):
            element = doc.GetElement(elem_id)
            row_data = []
            rendered_row = rendered_rows[row_idx] if row_idx < len(rendered_rows) else None

            for i, field_info in enumerate(fields_info):
                if field_info['schedulable']:
                    param = ScheduleDataExtractor._get_parameter(element, field_info['schedulable'])
                    value = ScheduleDataExtractor._get_param_value(param) if param else ""
                    storage_type = param.StorageType if param else None
                    is_readonly = param.IsReadOnly if param else True
                    if param is not None and not param.IsReadOnly:
                        field_has_editable_param[i] = True
                else:
                    value = ""
                    param = None
                    storage_type = None
                    is_readonly = True

                # Fallback: campo calculado ou somente-leitura sem parametro
                # acessivel -> usar o texto que o Revit renderiza na tabela
                if not value and rendered_row is not None:
                    col_idx = visible_col_index.get(i)
                    if col_idx is not None and col_idx < len(rendered_row):
                        value = rendered_row[col_idx]

                row_data.append({
                    'value': value,
                    'param': param,
                    'storage_type': storage_type,
                    'readonly': is_readonly,
                    'element': element
                })

            data_matrix.append(row_data)

        # Consolidar o read-only NO CAMPO (o grid cria colunas a partir daqui).
        # Sem isso a coluna nasce editavel e o usuario digita num campo que o
        # APPLY nao consegue gravar.
        for i, field_info in enumerate(fields_info):
            field_info['readonly'] = not field_has_editable_param[i]

        return element_ids, fields_info, data_matrix
    
    @staticmethod
    def _get_parameter(element, schedulable_field):
        """Get parameter from element"""
        try:
            param_id = schedulable_field.ParameterId
            param = element.get_Parameter(param_id)
            if param:
                return param
        except Exception as e:
            pass
        
        try:
            field_name = schedulable_field.GetName(doc)
            return element.LookupParameter(field_name)
        except Exception as e:
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


# ==================== COLUMN FILTER DIALOG ====================

class ColumnFilterDialog(forms.WPFWindow):
    """Filtro de coluna estilo Excel: sort A-Z/Z-A, busca e lista de valores.

    Resultado apos ShowDialog():
      - requested_sort: True (A-Z), False (Z-A) ou None
      - selected_values: set de valores permitidos, ou None = sem filtro
      - confirmed: False se o usuario cancelou
    """

    def __init__(self, column_name, values, current_filter):
        xaml_path = script.get_bundle_file('ui_column_filter.xaml')
        forms.WPFWindow.__init__(self, xaml_path)

        self.Title = "Filtro: {}".format(column_name)
        self.requested_sort = None
        self.selected_values = None
        self.confirmed = False

        self._checkboxes = []

        # Sem filtro ativo = tudo marcado
        all_selected = not current_filter

        for value in values:
            checkbox = CheckBox()
            checkbox.Content = value
            checkbox.IsChecked = all_selected or (value in current_filter)
            checkbox.Margin = Thickness(6, 3, 6, 3)
            checkbox.FontSize = 12
            self._checkboxes.append(checkbox)
            self.valuePanel.Children.Add(checkbox)

        self.chkSelectAll.IsChecked = all_selected

        self.btnSortAZ.Click += self._on_sort_az
        self.btnSortZA.Click += self._on_sort_za
        self.btnOk.Click += self._on_ok
        self.btnCancel.Click += self._on_cancel
        self.chkSelectAll.Click += self._on_select_all
        self.txtSearch.TextChanged += self._on_search

    def _on_sort_az(self, sender, e):
        self.requested_sort = True
        self.confirmed = True
        self.Close()

    def _on_sort_za(self, sender, e):
        self.requested_sort = False
        self.confirmed = True
        self.Close()

    def _on_select_all(self, sender, e):
        """Marca/desmarca apenas o que esta visivel na busca atual"""
        check = self.chkSelectAll.IsChecked
        for checkbox in self._checkboxes:
            if checkbox.Visibility == Visibility.Visible:
                checkbox.IsChecked = check

    def _on_search(self, sender, e):
        search = (self.txtSearch.Text or "").strip().lower()
        for checkbox in self._checkboxes:
            visible = not search or search in str(checkbox.Content).lower()
            checkbox.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _on_ok(self, sender, e):
        selected = set()
        all_checked = True

        for checkbox in self._checkboxes:
            if checkbox.IsChecked:
                selected.add(str(checkbox.Content))
            else:
                all_checked = False

        # Tudo marcado = nenhum filtro (evita filtro inutil no predicate)
        self.selected_values = None if all_checked else selected
        self.confirmed = True
        self.Close()

    def _on_cancel(self, sender, e):
        self.confirmed = False
        self.Close()


# ==================== MAIN WINDOW ====================

class RevitSheetProWindow(forms.WPFWindow):
    """Main window for RevitSheet Pro - v2.6 STABLE"""
    
    def __init__(self, schedule, all_schedules=None):
        """Initialize window with schedule data"""
        self.schedule = None
        self.data_manager = DataManager()
        self.current_cell_value = None
        self._clipboard_cells = []  # [(field_name, value), ...]
        self._column_field_map = {}  # DataGridColumn -> field_info
        self._collection_view = None
        self._items_list = None
        self._local_sort = None      # (field_name, ascending) ou None
        self._column_filters = {}    # field_name -> set de valores permitidos
        self._is_loading = True      # trava handlers durante a carga

        self._all_schedules = all_schedules or ScheduleDataExtractor.get_all_schedules()

        # Load XAML
        xaml_path = script.get_bundle_file('ui.xaml')
        forms.WPFWindow.__init__(self, xaml_path)

        # Popular o seletor de schedules do header
        for sched in self._all_schedules:
            self.cmbSchedule.Items.Add(sched.Name)

        # Handlers estaticos: ligados uma unica vez
        self._setup_event_handlers()

        # Carrega o schedule inicial (sincroniza o combo sem disparar troca)
        self.load_schedule(schedule)

    def _index_of_schedule(self, schedule):
        """Indice do schedule na lista, comparando por Id (nao por referencia)"""
        if schedule is None:
            return -1
        for i, sched in enumerate(self._all_schedules):
            if sched.Id == schedule.Id:
                return i
        return -1

    def load_schedule(self, schedule):
        """(Re)carrega um schedule na janela, sem fechar/reabrir.

        Idempotente: pode ser chamado quantas vezes for preciso. Limpa colunas,
        filtros e ordenacao do schedule anterior.
        """
        self._is_loading = True
        try:
            self.schedule = schedule

            # Estado visual do schedule anterior nao vale para o novo
            self._column_filters = {}
            self._local_sort = None

            self.loadingOverlay.Visibility = Visibility.Visible
            self.loadingText.Text = "Carregando schedule..."

            # Sincronizar o combo (sem disparar _on_schedule_changed)
            index = self._index_of_schedule(schedule)
            if index >= 0 and self.cmbSchedule.SelectedIndex != index:
                self.cmbSchedule.SelectedIndex = index

            self._load_schedule_data()
            self._setup_ui()

            self.loadingOverlay.Visibility = Visibility.Collapsed
        finally:
            self._is_loading = False

        self._update_ui_state()

        # Schedule vazio nao e erro: apenas avisar (antes o script abortava)
        if not self.element_ids:
            self.statusText.Text = ("Schedule '{}' nao tem elementos"
                                    .format(schedule.Name))
        else:
            self.statusText.Text = "Carregado: {}".format(schedule.Name)

        self._warn_if_linked_elements(schedule)

    def _warn_if_linked_elements(self, schedule):
        """Avisa quando o schedule inclui elementos de modelos vinculados.

        A API do Revit NAO permite editar parametros de elementos de link a
        partir do host. Essas linhas nao aparecem aqui e nao teriam como ser
        editadas — o usuario precisa saber que ve um subconjunto.
        """
        try:
            if not schedule.Definition.IncludeLinkedFiles:
                return
        except Exception:
            return

        aviso = ("Este schedule inclui elementos de modelos VINCULADOS.\n\n"
                 "Somente os {} elementos do modelo atual sao exibidos e "
                 "editaveis.\n\n"
                 "As linhas vindas de vinculos nao aparecem: a API do Revit nao "
                 "permite editar parametros de elementos vinculados a partir do "
                 "modelo host."
                 .format(len(self.element_ids)))

        self.statusText.Text = ("Carregado: {} (somente elementos do modelo "
                                "atual — schedule tem vinculos)"
                                .format(schedule.Name))
        forms.alert(aviso, title="Schedule com elementos vinculados")

    def _on_schedule_changed(self, sender, e):
        """Troca de schedule pelo combo do header, com guarda de pendencias"""
        if self._is_loading:
            return

        index = self.cmbSchedule.SelectedIndex
        if index < 0 or index >= len(self._all_schedules):
            return

        new_schedule = self._all_schedules[index]
        if self.schedule and new_schedule.Id == self.schedule.Id:
            return

        # Alteracoes pendentes seriam perdidas: confirmar antes
        if self.data_manager.GetModificationCount() > 0:
            confirmed = forms.alert(
                "Ha alteracoes pendentes que ainda nao foram aplicadas.\n\n"
                "Trocar de schedule e descartar essas alteracoes?",
                title="Alteracoes pendentes",
                yes=True, no=True
            )
            if not confirmed:
                # Reverter o combo para o schedule atual
                self._is_loading = True
                try:
                    old_index = self._index_of_schedule(self.schedule)
                    if old_index >= 0:
                        self.cmbSchedule.SelectedIndex = old_index
                finally:
                    self._is_loading = False
                return

        self.load_schedule(new_schedule)
        self.statusText.Text = "Schedule carregado: {}".format(new_schedule.Name)


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
        """Monta o grid para o schedule atual (idempotente: pode repetir)"""
        # Update header
        self.elementCountText.Text = "{} elements".format(len(self.element_ids))
        self.fieldCountText.Text = "{} fields".format(
            len([f for f in self.fields_info if not f['hidden']])
        )

        # Setup DataGrid columns with visual styling
        self._setup_datagrid_columns()

        # Setup filter ComboBox
        self.cmbFilterColumn.Items.Clear()
        self.cmbFilterColumn.Items.Add("All Columns")
        for field in self.fields_info:
            if not field['hidden']:
                self.cmbFilterColumn.Items.Add(field['name'])
        self.cmbFilterColumn.SelectedIndex = 0

        # Limpar busca do schedule anterior
        self.txtQuickFilter.Text = ""
        self.chkShowModifiedOnly.IsChecked = False
        
        # Convert items to list for DataGrid
        items_list = List[object]()
        for item in self.data_manager.items:
            items_list.Add(item)
        self._items_list = items_list

        # Bind via ICollectionView: filtrar/ordenar sem reconstruir a lista
        # (rebind manual de ItemsSource perde selecao, scroll e ordenacao)
        self._collection_view = CollectionViewSource.GetDefaultView(items_list)
        self._collection_view.Filter = Predicate[object](self._filter_predicate)
        self.mainDataGrid.ItemsSource = self._collection_view
        # NAO ligar eventos aqui: _setup_ui roda a cada troca de schedule e
        # os handlers acumulariam. Eventos ficam em _setup_event_handlers.


    def _setup_datagrid_columns(self):
        """Create DataGrid columns with read-only visual styling"""
        # Limpar colunas do schedule anterior (senao acumulam na troca)
        self.mainDataGrid.Columns.Clear()
        self._column_field_map = {}

        # Style for read-only cells (fundo azul claro, como na versao C#)
        readonly_style = Style(TargetType=DataGridCell)
        readonly_style.Setters.Add(Setter(
            DataGridCell.BackgroundProperty,
            SolidColorBrush(Color.FromRgb(232, 240, 254))  # #E8F0FE
        ))
        readonly_style.Setters.Add(Setter(
            DataGridCell.CursorProperty,
            Cursors.Arrow
        ))

        # Cor do texto vai no ElementStyle (TextBlock interno), NAO no
        # DataGridCell: Foreground no cell nao pinta o texto renderizado.
        readonly_text_style = Style(TargetType=TextBlock)
        readonly_text_style.Setters.Add(Setter(
            TextBlock.ForegroundProperty,
            SolidColorBrush(Color.FromRgb(55, 71, 79))  # #37474F
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
            
            # Determine if read-only
            is_readonly = field_info.get('readonly', False) or not field_info.get('can_edit', True)

            # Create binding (OneWay em coluna read-only: nao ha o que gravar)
            binding = Binding("[{}]".format(field_info['name']))
            binding.Mode = BindingMode.OneWay if is_readonly else BindingMode.TwoWay
            binding.UpdateSourceTrigger = UpdateSourceTrigger.LostFocus

            column.Binding = binding
            column.IsReadOnly = is_readonly
            
            # Apply visual style
            column.CellStyle = readonly_style if is_readonly else editable_style
            if is_readonly:
                column.ElementStyle = readonly_text_style
            
            # Add to grid
            self.mainDataGrid.Columns.Add(column)

            # Registrar vinculo coluna -> campo.
            # NUNCA usar DisplayIndex para resolver o campo: ele muda quando o
            # usuario reordena colunas e a escrita cai no parametro errado.
            self._column_field_map[column] = field_info

    def _get_field_for_column(self, column):
        """Resolve o field_info de uma coluna do grid (None se nao mapeada).

        Usa o mapa registrado na criacao das colunas. Fallback: le o nome
        do campo do Path do Binding ("[Nome]" -> "Nome").
        """
        if column is None:
            return None

        field_info = self._column_field_map.get(column)
        if field_info:
            return field_info

        # Fallback pelo Binding.Path
        try:
            path = column.Binding.Path.Path  # "[Nome do Campo]"
            if path.startswith("[") and path.endswith("]"):
                path = path[1:-1]
            for fi in self.fields_info:
                if fi['name'] == path:
                    return fi
        except Exception:
            pass

        return None

    def _get_field_name_for_column(self, column):
        """Nome do campo de uma coluna, ou None."""
        field_info = self._get_field_for_column(column)
        return field_info['name'] if field_info else None

    def _setup_event_handlers(self):
        """Liga os eventos. Chamado UMA vez, no __init__."""
        # Troca de schedule pelo header
        self.cmbSchedule.SelectionChanged += self._on_schedule_changed

        # Selecao de celulas
        self.mainDataGrid.SelectionChanged += self._on_selection_changed

        # File operations
        self.btnExportCsv.Click += self._on_export_csv
        self.btnImportCsv.Click += self._on_import_csv
        self.btnExportXlsx.Click += self._on_export_xlsx
        self.btnImportXlsx.Click += self._on_import_xlsx
        
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
        
        # Reset All
        self.btnResetAll.Click += self._on_reset_all

        # DataGrid events
        self.mainDataGrid.BeginningEdit += self._on_beginning_edit
        self.mainDataGrid.CellEditEnding += self._on_cell_edit_ending

        # Sort local (clique no header) e filtro de coluna (botao direito)
        self.mainDataGrid.Sorting += self._on_datagrid_sorting
        self.mainDataGrid.PreviewMouseRightButtonUp += self._on_datagrid_right_click

        # Numero da linha no row header (RowHeaderWidth ja reservado no XAML)
        self.mainDataGrid.LoadingRow += self._on_loading_row

        # Keyboard shortcuts
        self.PreviewKeyDown += self._on_key_down
    
    def _on_key_down(self, sender, e):
        """Handle keyboard shortcuts"""
        if e.KeyboardDevice.Modifiers == ModifierKeys.Control:
            if e.Key == Key.C:
                self._on_copy_cells()
                e.Handled = True
            elif e.Key == Key.V:
                self._on_paste_cells()
                e.Handled = True
            elif e.Key == Key.Z:
                self._on_undo(None, None)
                e.Handled = True
            elif e.Key == Key.Y:
                self._on_redo(None, None)
                e.Handled = True
            elif e.Key == Key.F:
                self._on_find_replace(None, None)
                e.Handled = True
            elif e.Key == Key.S:
                self._on_export_csv(None, None)
                e.Handled = True
        elif e.Key == Key.Delete:
            self._on_clear_selected(None, None)
            e.Handled = True

    def _on_copy_cells(self):
        """Copy selected cells to system clipboard as TSV (Excel-compatible)"""
        selected_cells = self.mainDataGrid.SelectedCells
        if not selected_cells:
            return

        # Organizar celulas por (row_index, col_index) para manter grid
        cell_map = {}  # (row_idx, col_idx) -> value
        items_order = []  # manter ordem dos items
        items_seen = {}

        for cell in selected_cells:
            item = cell.Item
            # DisplayIndex serve APENAS para posicionar a celula no TSV.
            # O campo vem do mapa da coluna (ver _get_field_for_column).
            col_index = cell.Column.DisplayIndex
            field_name = self._get_field_name_for_column(cell.Column)
            if not field_name:
                continue

            # Mapear item para row index
            item_id = id(item)
            if item_id not in items_seen:
                items_seen[item_id] = len(items_order)
                items_order.append(item)
            row_idx = items_seen[item_id]

            value = ""
            if hasattr(item, 'GetValue'):
                value = item.GetValue(field_name) or ""
            cell_map[(row_idx, col_index)] = str(value)

        if not cell_map:
            return

        # Determinar bounds do grid copiado
        min_row = min(r for r, c in cell_map)
        max_row = max(r for r, c in cell_map)
        min_col = min(c for r, c in cell_map)
        max_col = max(c for r, c in cell_map)

        # Construir TSV (tab-separated)
        rows = []
        for r in range(min_row, max_row + 1):
            cols = []
            for c in range(min_col, max_col + 1):
                cols.append(cell_map.get((r, c), ""))
            rows.append("\t".join(cols))
        tsv_text = "\r\n".join(rows)

        # Copiar para clipboard sistema
        try:
            from System.Windows import Clipboard
            Clipboard.SetText(tsv_text)
        except Exception as e:
            pass

        total = len(cell_map)
        self.statusText.Text = "Copiadas {} celula(s) ({} linhas x {} colunas)".format(
            total, max_row - min_row + 1, max_col - min_col + 1)

    def _on_paste_cells(self):
        """Paste from system clipboard (TSV) to selected cells
        - 1 celula copiada -> cola em todas selecionadas
        - N celulas -> cola respeitando grid (linhas x colunas)
        """
        # Ler do clipboard sistema
        tsv_text = ""
        try:
            from System.Windows import Clipboard
            if Clipboard.ContainsText():
                tsv_text = Clipboard.GetText()
        except Exception as e:
            pass

        if not tsv_text:
            self.statusText.Text = "Clipboard vazio"
            return

        # Parse TSV em grid
        paste_rows = []
        for line in tsv_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if line:
                paste_rows.append(line.split("\t"))
        # Remover ultima linha vazia se houver
        if paste_rows and paste_rows[-1] == ['']:
            paste_rows.pop()

        if not paste_rows:
            self.statusText.Text = "Clipboard vazio"
            return

        selected_cells = self.mainDataGrid.SelectedCells
        if not selected_cells:
            return

        # DisplayIndex (posicao visual) -> field_info. Reconstruido a cada colagem
        # porque o usuario pode ter reordenado as colunas.
        display_to_field = {}
        for col in self.mainDataGrid.Columns:
            fi = self._get_field_for_column(col)
            if fi:
                display_to_field[col.DisplayIndex] = fi

        # Mapear celulas selecionadas para (row_idx, col_idx, item, field_info)
        items_order = []
        items_seen = {}
        sel_cells = []

        for cell in selected_cells:
            item = cell.Item
            # DisplayIndex so para posicao no grid colado; campo vem do mapa.
            col_index = cell.Column.DisplayIndex
            fi = self._get_field_for_column(cell.Column)
            if not fi:
                continue

            item_id = id(item)
            if item_id not in items_seen:
                items_seen[item_id] = len(items_order)
                items_order.append(item)
            row_idx = items_seen[item_id]

            if not fi.get('readonly') and fi.get('can_edit'):
                sel_cells.append((row_idx, col_index, item, fi['name']))

        if not sel_cells:
            self.statusText.Text = "Selecione celulas editaveis para colar."
            return

        commands = []
        paste_num_rows = len(paste_rows)
        paste_num_cols = max(len(r) for r in paste_rows)
        is_single = (paste_num_rows == 1 and paste_num_cols == 1)

        if is_single:
            # 1 valor -> colar em TODAS as celulas selecionadas
            paste_value = paste_rows[0][0]
            for row_idx, col_idx, item, field_name in sel_cells:
                old_value = item.GetValue(field_name) or ""
                if str(old_value) != paste_value:
                    commands.append(
                        ChangeCommand(item, field_name, old_value, paste_value))
        else:
            # Multi-cell: mapear grid colado sobre grid selecionado
            # Anchor = celula selecionada com menor (row, col)
            min_sel_row = min(r for r, c, i, f in sel_cells)
            min_sel_col = min(c for r, c, i, f in sel_cells)

            # Construir lookup rapido das celulas selecionadas
            sel_lookup = {}
            for row_idx, col_idx, item, field_name in sel_cells:
                sel_lookup[(row_idx, col_idx)] = (item, field_name)

            # Mapear paste grid sobre selecao a partir do anchor
            for pr in range(paste_num_rows):
                if pr >= len(paste_rows):
                    continue
                for pc in range(len(paste_rows[pr])):
                    target_row = min_sel_row + pr
                    target_col = min_sel_col + pc

                    target = sel_lookup.get((target_row, target_col))
                    if not target:
                        # Celula nao selecionada, tentar encontrar item pela ordem
                        fi = display_to_field.get(target_col)
                        if fi and target_row < len(items_order):
                            if not fi.get('readonly') and fi.get('can_edit'):
                                target = (items_order[target_row], fi['name'])

                    if target:
                        item, field_name = target
                        paste_value = paste_rows[pr][pc]
                        old_value = item.GetValue(field_name) or ""
                        if str(old_value) != paste_value:
                            commands.append(
                                ChangeCommand(item, field_name, old_value, paste_value))

        if commands:
            batch = BatchChangeCommand(commands)
            self.data_manager.undo_manager.ExecuteCommand(batch)
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Coladas {} celula(s)".format(len(commands))
        else:
            self.statusText.Text = "Nenhuma alteracao ao colar"

    def _on_reset_all(self, sender, e):
        """Reset all modifications to original values"""
        modified = self.data_manager.GetModifiedItems()
        if not modified:
            forms.alert("Nenhuma modificacao pendente.")
            return
        result = forms.alert(
            "Reverter todas as {} modificacoes?".format(
                self.data_manager.GetModificationCount()
            ),
            yes=True, no=True
        )
        if not result:
            return
        self.data_manager.ResetAllToOriginal()
        self._refresh_grid()
        self._update_ui_state()
        self.statusText.Text = "Todas as modificacoes revertidas"

    def _on_beginning_edit(self, sender, e):
        """Store value before editing"""
        row = e.Row.DataContext
        field_name = self._get_field_name_for_column(e.Column)
        if not field_name:
            self.current_cell_value = None
            return

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

        # Get field info
        field_name = self._get_field_name_for_column(e.Column)
        if not field_name:
            return

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
    
    def _on_loading_row(self, sender, e):
        """Numera a linha no row header (1-based, segue a ordem visivel)"""
        e.Row.Header = str(e.Row.GetIndex() + 1)

    def _on_selection_changed(self, sender, e):
        """Handle selection change"""
        selected_count = self.mainDataGrid.SelectedCells.Count
        if selected_count == 0:
            self.txtSelectionInfo.Text = "No selection"
        elif selected_count == 1:
            self.txtSelectionInfo.Text = "1 cell selected"
        else:
            self.txtSelectionInfo.Text = "{} cells selected".format(selected_count)
    
    def _on_datagrid_right_click(self, sender, e):
        """Botao direito no header da coluna -> filtro estilo Excel"""
        element = e.OriginalSource

        # Subir a VisualTree ate achar o header da coluna
        while element is not None and not isinstance(element, DataGridColumnHeader):
            try:
                element = VisualTreeHelper.GetParent(element)
            except Exception:
                return

        if element is None or element.Column is None:
            return

        e.Handled = True
        self._show_column_filter(element.Column)

    def _show_column_filter(self, column):
        """Abre o dialogo de filtro para uma coluna"""
        field_name = self._get_field_name_for_column(column)
        if not field_name:
            return

        # Valores distintos, ignorando vazios
        values = set()
        for item in self.data_manager.items:
            value = str(item.GetValue(field_name) or "").strip()
            if value:
                values.add(value)

        if not values:
            self.statusText.Text = "Coluna '{}' nao tem valores para filtrar".format(field_name)
            return

        values = sorted(values, key=_sort_key)
        current_filter = self._column_filters.get(field_name)

        dialog = ColumnFilterDialog(field_name, values, current_filter)
        dialog.Owner = self
        dialog.ShowDialog()

        if not dialog.confirmed:
            return

        # Pediu ordenacao em vez de filtro
        if dialog.requested_sort is not None:
            self._set_local_sort(field_name, dialog.requested_sort)
            direction = "crescente" if dialog.requested_sort else "decrescente"
            self.statusText.Text = "Ordem: {} ({})".format(field_name, direction)
            return

        # Aplicou filtro de valores
        if dialog.selected_values is None:
            self._column_filters.pop(field_name, None)
        else:
            self._column_filters[field_name] = dialog.selected_values

        if self._collection_view:
            self._collection_view.Refresh()

        active = len(self._column_filters)
        self.statusText.Text = ("Filtros de coluna ativos: {}".format(active)
                                if active else "Filtros de coluna limpos")

    def _on_datagrid_sorting(self, sender, e):
        """Clique no header: cicla crescente -> decrescente -> sem ordem.

        e.Handled = True porque o sort padrao do DataGrid nao funciona com
        binding por indexer (ver ScheduleItemComparer).
        """
        e.Handled = True

        field_name = self._get_field_name_for_column(e.Column)
        if not field_name:
            return

        if self._local_sort and self._local_sort[0] == field_name:
            # Mesma coluna: avanca no ciclo
            self._local_sort = (field_name, False) if self._local_sort[1] else None
        else:
            self._local_sort = (field_name, True)

        self._apply_local_sort()

        if not self._local_sort:
            self.statusText.Text = "Ordenacao removida: {}".format(field_name)
        else:
            direction = "crescente" if self._local_sort[1] else "decrescente"
            self.statusText.Text = "Ordem: {} ({})".format(field_name, direction)

    def _set_local_sort(self, field_name, ascending):
        """Define a ordenacao diretamente (usado pela janela de filtro)"""
        self._local_sort = (field_name, ascending)
        self._apply_local_sort()

    def _apply_local_sort(self):
        """Aplica CustomSort no CollectionView e atualiza as setas nos headers"""
        if not self._collection_view:
            return

        if self._local_sort:
            field_name, ascending = self._local_sort
            # Setar CustomSort ja dispara Refresh internamente
            self._collection_view.CustomSort = ScheduleItemComparer(field_name, ascending)
        else:
            self._collection_view.CustomSort = None
            self._collection_view.Refresh()

        # Indicador visual (seta) no header da coluna ordenada
        for column in self.mainDataGrid.Columns:
            column_field = self._get_field_name_for_column(column)
            if self._local_sort and column_field == self._local_sort[0]:
                column.SortDirection = (ListSortDirection.Ascending
                                        if self._local_sort[1]
                                        else ListSortDirection.Descending)
            else:
                column.SortDirection = None

    def _on_filter_changed(self, sender, e):
        """Reavalia o filtro do CollectionView (sem reconstruir a lista)"""
        if self._is_loading:
            return
        if self._collection_view:
            self._collection_view.Refresh()

    def _filter_predicate(self, obj):
        """Predicate do CollectionView: True = item visivel no grid.

        Combina: 'somente modificados' + quick filter (coluna unica ou todas).
        """
        item = obj
        if item is None:
            return False

        # Filtro 'somente modificados'
        if self.chkShowModifiedOnly.IsChecked and not item.IsModified:
            return False

        # Filtros de coluna (botao direito no header)
        for field_name, allowed in self._column_filters.items():
            value = str(item.GetValue(field_name) or "").strip()
            if value not in allowed:
                return False

        # Quick filter
        filter_text = (self.txtQuickFilter.Text or "").strip().lower()
        if not filter_text:
            return True

        filter_column = self.cmbFilterColumn.SelectedItem

        if not filter_column or filter_column == "All Columns":
            for field in self.fields_info:
                if not field['hidden']:
                    value = str(item.GetValue(field['name']) or "").lower()
                    if filter_text in value:
                        return True
            return False

        value = str(item.GetValue(filter_column) or "").lower()
        return filter_text in value
    
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
        """Reavalia filtro/ordenacao e redesenha as celulas.

        Com CollectionView nao ha rebind: a selecao e o scroll sao preservados.
        """
        if self._collection_view:
            self._collection_view.Refresh()
        else:
            self.mainDataGrid.Items.Refresh()
    
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
            if isinstance(result, dict):
                changes = result.get('changes', 0)
                matched_rows = result.get('matched_rows', 0)
                skipped_rows = result.get('skipped_rows', 0)
                matched_cols = result.get('matched_cols', [])
                skipped_cols = result.get('skipped_cols', [])

                lines = []
                if changes > 0:
                    lines.append("{} alteracoes aplicadas.".format(changes))
                    lines.append("{} linhas correspondentes, {} ignoradas.".format(
                        matched_rows, skipped_rows))
                    if skipped_cols:
                        lines.append("\nColunas ignoradas (nao existem no schedule):")
                        for col in sorted(skipped_cols):
                            lines.append("  - {}".format(col))
                    forms.alert("\n".join(lines))
                    self._refresh_grid()
                    self._update_ui_state()
                    self.statusText.Text = "Imported {} changes from CSV".format(changes)
                else:
                    msg = "Nenhuma alteracao encontrada no CSV."
                    if skipped_rows > 0:
                        msg += "\n{} linhas sem correspondencia.".format(skipped_rows)
                    if skipped_cols:
                        msg += "\nColunas ignoradas: {}".format(", ".join(sorted(skipped_cols)))
                    forms.alert(msg)
            else:
                forms.alert("Nenhuma alteracao encontrada no CSV.")
        else:
            forms.alert("Erro no import:\n{}".format(result), exitscript=False)
    
    def _on_export_xlsx(self, sender, e):
        """Export para .xlsx (imune ao separador de lista do Windows)"""
        safe_name = self.schedule.Name
        for char in '\\/:*?"<>|':
            safe_name = safe_name.replace(char, '_')

        file_path = forms.save_file(
            file_ext='xlsx',
            default_name='{}_export.xlsx'.format(safe_name)
        )

        if not file_path:
            return

        success, error = self.data_manager.ExportToXLSX(
            file_path, sheet_name=self.schedule.Name)

        if not success:
            forms.alert("Erro ao exportar Excel:\n{}".format(error), exitscript=False)
            return

        self.statusText.Text = "Exportado para Excel"

        abrir = forms.alert(
            "Exportado com sucesso:\n{}\n\nAbrir o arquivo agora?".format(file_path),
            yes=True, no=True
        )
        if abrir:
            try:
                os.startfile(file_path)
            except Exception as ex:
                forms.alert("Arquivo salvo, mas nao foi possivel abrir:\n{}".format(ex),
                            exitscript=False)

    def _on_import_xlsx(self, sender, e):
        """Import de .xlsx (mesmo contrato do import CSV)"""
        file_path = forms.pick_file(file_ext='xlsx')

        if not file_path:
            return

        confirmado = forms.alert(
            "O import sobrescreve as celulas correspondentes.\nContinuar?",
            yes=True, no=True
        )
        if not confirmado:
            return

        success, result = self.data_manager.ImportFromXLSX(file_path)

        if not success:
            forms.alert("Erro no import:\n{}".format(result), exitscript=False)
            return

        changes = result.get('changes', 0)
        matched_rows = result.get('matched_rows', 0)
        skipped_rows = result.get('skipped_rows', 0)
        skipped_cols = result.get('skipped_cols', [])

        if changes > 0:
            lines = ["{} alteracoes aplicadas.".format(changes),
                     "{} linhas correspondentes, {} ignoradas.".format(
                         matched_rows, skipped_rows)]
            if skipped_cols:
                lines.append("\nColunas ignoradas (nao existem no schedule):")
                for col in sorted(skipped_cols):
                    lines.append("  - {}".format(col))
            forms.alert("\n".join(lines))
            self._refresh_grid()
            self._update_ui_state()
            self.statusText.Text = "Importadas {} alteracoes do Excel".format(changes)
        else:
            msg = "Nenhuma alteracao encontrada na planilha."
            if skipped_rows > 0:
                msg += "\n{} linhas sem correspondencia.".format(skipped_rows)
            if skipped_cols:
                msg += "\nColunas ignoradas: {}".format(", ".join(sorted(skipped_cols)))
            forms.alert(msg)

    def _on_find_replace(self, sender, e):
        """Show find and replace dialog - v2.6 FIXED"""
        try:
            output.print_md("---")
            output.print_md("## 🔍 Find & Replace")
            
            # Get visible column names
            visible_columns = [f['name'] for f in self.fields_info if not f['hidden']]
            
            output.print_md("**Available columns:** {}".format(len(visible_columns)))
            
            # Create and show dialog with match count support
            dialog = FindReplaceDialog(visible_columns, data_manager=self.data_manager)
            
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
            use_regex = dialog.use_regex

            # Determine column name
            column_name = None if selected_column == "All Columns" else selected_column

            # Perform find and replace
            count = self.data_manager.FindAndReplace(
                find_text, replace_text, column_name,
                use_regex=use_regex, case_sensitive=case_sensitive
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
            field_name = self._get_field_name_for_column(cell.Column)
            if field_name:
                columns.add(field_name)
        
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
        column_name = self._get_field_name_for_column(selected_cells[0].Column)
        if not column_name:
            return

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

            field_info = self._get_field_for_column(cell.Column)
            if not field_info:
                continue
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
                        # Set parameter value via SetValueString (handles units/formatting)
                        storage = param.StorageType
                        if storage == StorageType.String:
                            param.Set(str(new_value))
                        else:
                            # SetValueString handles Double/Integer/ElementId with unit conversion
                            if not param.SetValueString(str(new_value)):
                                # Fallback for Integer
                                if storage == StorageType.Integer:
                                    param.Set(int(float(new_value)))
                                elif storage == StorageType.Double:
                                    # Fallback: tentar converter diretamente
                                    try:
                                        param.Set(float(new_value))
                                    except Exception as e:
                                        errors.append("Falha ao definir '{}' = '{}' no elem {} (Double)".format(
                                            field_name, new_value, item.ElementIdValue
                                        ))
                                        continue
                                else:
                                    errors.append("Falha ao definir '{}' = '{}' no elem {} (SetValueString)".format(
                                        field_name, new_value, item.ElementIdValue
                                    ))
                                    continue

                        success_count += 1

                    except Exception as ex:
                        errors.append("Erro em '{}' elem {}: {}".format(
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
    try:
        """Main execution function"""
        output.print_md("## RevitSheet Pro v4.0")
        output.print_md("---")
    
        # Get all schedules
        schedules = ScheduleDataExtractor.get_all_schedules()
    
        if not schedules:
            forms.alert("❌ No schedules found in the current document.", exitscript=True)
    
        # Schedule inicial: a view ativa, se for um schedule; senao o primeiro.
        # A troca passa a ser feita pelo combo do header, sem fechar a janela.
        selected_schedule = schedules[0]

        active_view = doc.ActiveView
        if isinstance(active_view, ViewSchedule):
            for sched in schedules:
                if sched.Id == active_view.Id:
                    selected_schedule = sched
                    break

        output.print_md("**Opening:** {}".format(selected_schedule.Name))

        # Launch editor window
        try:
            window = RevitSheetProWindow(selected_schedule, all_schedules=schedules)
            window.ShowDialog()
        
            output.print_md("---")
            output.print_md("✅ **Session completed successfully**")
        
        except Exception as ex:
            output.print_md("❌ **Error:** {}".format(str(ex)))
            import traceback
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
# ==================== RUN ====================
if __name__ == '__main__':
    main()
