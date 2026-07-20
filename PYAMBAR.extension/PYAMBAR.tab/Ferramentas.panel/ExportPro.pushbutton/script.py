# -*- coding: utf-8 -*-
__title__ = "Export Pro"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "2.1"

import os
import sys
import traceback

import clr

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System')

from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import forms, revit, script

from System.Windows import (
    Thickness, FontWeights, VerticalAlignment, HorizontalAlignment,
    GridLength, GridUnitType,
)
from System.Windows.Controls import (
    StackPanel, Border, TextBlock, ComboBox, Button, TextBox,
    CheckBox, Grid, ColumnDefinition, RowDefinition, ScrollViewer,
    Orientation as WPFOrientation,
)
from System.Windows.Controls.Primitives import Popup, PlacementMode
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Input import Keyboard, ModifierKeys

doc = revit.doc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

if PATH_SCRIPT not in sys.path:
    sys.path.insert(0, PATH_SCRIPT)

from ExportPro import (
    config_manager,
    csv_exporter,
    excel_exporter,
    gas_client,
)
from ExportPro.grouping_engine import apply_grouping, apply_filters
from ExportPro.schedule_reader import get_all_schedules, read_schedule

# -- CONSTANTES DE COR ---------------------------------------------------------

_C_HDR_BG  = Color.FromRgb(31,  78,  121)   # #1F4E79
_C_HDR_FG  = Color.FromRgb(255, 255, 255)
_C_ALT_BG  = Color.FromRgb(248, 250, 252)   # #F8FAFC
_C_SEP     = Color.FromRgb(226, 232, 240)   # #E2E8F0
_C_CTRL_BG = Color.FromRgb(241, 245, 249)   # #F1F5F9

# -- PALAVRAS-CHAVE PARA DETECAO AUTOMATICA ------------------------------------

_SUM_KEYWORDS = {
    'count', 'quantidade', 'qtt', 'qt', 'qtd', 'qty',
    'comprimento', 'length', 'area', 'volume',
    'peso', 'weight', 'custo', 'cost', 'valor', 'value',
    'price', 'preco', 'total', 'sum', 'soma',
    'vazao', 'flow', 'potencia', 'power',
}


def _smart_action(col_name):
    lower = col_name.lower()
    for w in _SUM_KEYWORDS:
        if w in lower:
            return 'Somar'
    return 'Agrupar'


# -- MODELOS -------------------------------------------------------------------

class ColumnRule(object):
    ACTIONS = ['Agrupar', 'Somar', 'Contar', 'Manter', 'Ignorar']
    ACTION_MAP = {'Agrupar': 'group', 'Somar': 'sum', 'Contar': 'count', 'Manter': 'manter', 'Ignorar': 'ignore'}
    ACTION_REVERSE = {'group': 'Agrupar', 'sum': 'Somar', 'count': 'Contar', 'manter': 'Manter',
                      'ignore': 'Ignorar', 'copy_first': 'Agrupar'}
    DIR_TO_INTERNAL   = {'↑': 'ASC', '↓': 'DESC', 'ASC': 'ASC', 'DESC': 'DESC'}
    DIR_FROM_INTERNAL = {'ASC': '↑', 'DESC': '↓'}

    def __init__(self, name, action='Agrupar', sort_order='', sort_dir='↑'):
        self.Name      = name
        self.Action    = action
        self.SortOrder = sort_order
        self.SortDir   = sort_dir
        self.FilterExcluded = set()   # valores desmarcados no filtro (sessao apenas, nao vai a preset)

    def to_rule_dict(self):
        action_key = self.ACTION_MAP.get(self.Action, 'ignore')
        try:
            order = int(self.SortOrder) if self.SortOrder else None
        except ValueError:
            order = None
        return {
            'name':       self.Name,
            'action':     action_key,
            'sort_order': order,
            'sort_dir':   self.DIR_TO_INTERNAL.get(self.SortDir, 'ASC'),
            'filter_excluded': sorted(self.FilterExcluded) if self.FilterExcluded else None,
        }

    @classmethod
    def from_rule_dict(cls, d):
        action_label = cls.ACTION_REVERSE.get(d.get('action', 'ignore'), 'Agrupar')
        order = str(d.get('sort_order', '')) if d.get('sort_order') is not None else ''
        arrow = cls.DIR_FROM_INTERNAL.get(str(d.get('sort_dir', 'ASC')).upper(), '↑')
        return cls(name=d['name'], action=action_label, sort_order=order, sort_dir=arrow)


class ScheduleItem(object):
    """Representa um schedule na lista do Advanced Export."""
    def __init__(self, name, schedule_obj):
        self.name           = name
        self.schedule       = schedule_obj
        self.is_checked     = False
        self.include_header = True
        self.row_grid       = None  # referencia ao Grid da linha para highlight


def _unique_preview_rows(rows, n=5):
    """Retorna ate n linhas distintas (combinacao de todos os campos)."""
    seen = set()
    result = []
    for row in rows:
        key = tuple(row)
        if key not in seen:
            seen.add(key)
            result.append(row)
            if len(result) >= n:
                break
    return result


def _remap_rules_by_name(src_rules, dst_rules):
    """Copia action/sort de src para dst — nome da coluna primeiro, posicao como fallback.

    Filtros de valores NAO sao copiados do modelo: sao por schedule (preserva os do destino).
    """
    src_by_name = {r.Name: r for r in src_rules}
    result = []
    for i, dst in enumerate(dst_rules):
        if dst.Name in src_by_name:
            src = src_by_name[dst.Name]
        elif i < len(src_rules):
            src = src_rules[i]
        else:
            new_rule = ColumnRule(dst.Name, action=_smart_action(dst.Name))
            new_rule.FilterExcluded = set(dst.FilterExcluded)
            result.append(new_rule)
            continue
        new_rule = ColumnRule(dst.Name, action=src.Action,
                              sort_order=src.SortOrder, sort_dir=src.SortDir)
        new_rule.FilterExcluded = set(dst.FilterExcluded)
        result.append(new_rule)
    return result


def _rules_to_preset(rules):
    """Serializa regras para preset — filtros de valores ficam de fora (sessao apenas)."""
    out = []
    for r in rules:
        d = r.to_rule_dict()
        d.pop('filter_excluded', None)
        out.append(d)
    return out


# -- JANELA PRINCIPAL ----------------------------------------------------------

class ExportProWindow(forms.WPFWindow):

    def __init__(self):
        xaml_path = script.get_bundle_file('ui.xaml')
        forms.WPFWindow.__init__(self, xaml_path, handle_esc=True)

        self._schedules     = get_all_schedules(doc)
        self._cfg           = config_manager.load_config(doc)
        self._sched_items   = [ScheduleItem(s.Name, s) for s in self._schedules]
        self._rules_cache        = {}     # {schedule_name: list[ColumnRule]}
        self._data_cache         = {}     # {schedule_name: (headers, rows)} — evita releitura do Revit
        self._column_rules       = []     # regras do schedule atualmente exibido
        self._current_name       = None
        self._raw_headers        = []     # headers brutos do schedule atual
        self._raw_rows           = []     # linhas brutas do schedule atual
        self._same_rules_source  = None   # nome do schedule fonte das regras
        self._preview_refreshing = False  # guard contra re-entrada em _refresh_preview
        self._modelo_updating    = False  # guard contra loop chkModeloSource
        self._selected_cols      = set()  # indices de colunas selecionadas (multi-select)

        self._wire_events()
        self._setup_quick_tab()
        self._setup_advanced_tab()

    # -- SETUP -----------------------------------------------------------------

    def _setup_quick_tab(self):
        for sched in self._schedules:
            self.lstSchedules.Items.Add(sched.Name)

        self.txtFolder.Text = self._cfg.get('default_folder', '')

        for t in ['{projeto}_{schedule}', '{schedule}', '{projeto}', 'EXPORT_{schedule}']:
            self.cmbFilename.Items.Add(t)
        self.cmbFilename.Text = self._cfg.get('filename_template', '{projeto}_{schedule}')
        self.chkHeaders.IsChecked = self._cfg.get('include_headers', True)

        fmt = self._cfg.get('default_format', 'csv')
        if   fmt == 'excel': self.rdoExcel.IsChecked = True
        elif fmt == 'gas':   self.rdoGas.IsChecked   = True
        else:                self.rdoCsv.IsChecked   = True

    def _setup_advanced_tab(self):
        self._build_adv_schedule_list()
        self.txtAdvFolder.Text = self._cfg.get('default_folder', '')
        self.txtGasUrl.Text    = self._cfg.get('spreadsheet_url', '')

        # Carregar preset do projeto no cache
        project_preset = config_manager.load_project_preset(doc)
        for name, rules in project_preset.items():
            self._rules_cache[name] = [ColumnRule.from_rule_dict(r) for r in rules]

        # Carregar preview do primeiro schedule
        if self._sched_items:
            self._load_schedule_preview(self._sched_items[0].name)

    def _build_adv_schedule_list(self):
        _C_SRC = Color.FromRgb(220, 252, 231)   # #DCFCE7 verde claro — schedule fonte das regras
        sp = StackPanel()
        for item in self._sched_items:
            row = self._make_sched_list_row(item)
            if self._same_rules_source and item.name == self._same_rules_source:
                row.Background = SolidColorBrush(_C_SRC)
            sp.Children.Add(row)
        self.scvSchedules.Content = sp

    _C_ROW_NORMAL = Color.FromRgb(255, 255, 255)
    _C_ROW_SEL    = Color.FromRgb(219, 234, 254)   # #DBEAFE — azul claro selecionado

    def _make_sched_list_row(self, item):
        g = Grid()
        g.Margin     = Thickness(2, 1, 2, 1)
        g.Background = SolidColorBrush(self._C_ROW_NORMAL)
        item.row_grid = g

        for w in [GridLength.Auto, GridLength(1, GridUnitType.Star)]:
            cd = ColumnDefinition()
            cd.Width = w
            g.ColumnDefinitions.Add(cd)

        # Checkbox de selecao
        chk = CheckBox()
        chk.IsChecked       = item.is_checked
        chk.VerticalAlignment = VerticalAlignment.Center

        def _make_chk_handler(it):
            def h(s, e):
                it.is_checked = bool(s.IsChecked)
            return h

        chk.Checked   += _make_chk_handler(item)
        chk.Unchecked += _make_chk_handler(item)
        Grid.SetColumn(chk, 0)
        g.Children.Add(chk)

        # Nome
        tb = TextBlock()
        tb.Text              = item.name
        tb.FontSize          = 11
        tb.VerticalAlignment = VerticalAlignment.Center
        tb.Margin            = Thickness(4, 0, 4, 0)
        Grid.SetColumn(tb, 1)
        g.Children.Add(tb)

        # Clicar na linha carrega o preview (tunneling — dispara antes do CheckBox consumir o evento)
        def _make_row_click(n):
            def h(s, e):
                try:
                    self._load_schedule_preview(n)
                except Exception as ex:
                    self.txtStatusAdv.Text = 'Erro preview: {}'.format(str(ex))
            return h

        g.PreviewMouseLeftButtonDown += _make_row_click(item.name)

        return g

    # -- PREVIEW PANEL ---------------------------------------------------------

    def _load_schedule_preview(self, schedule_name):
        # Salvar regras atuais no cache
        if self._current_name and self._current_name != schedule_name:
            self._rules_cache[self._current_name] = list(self._column_rules)
            self._selected_cols = set()  # reset selecao ao trocar schedule

        self._current_name = schedule_name

        # Highlight da linha selecionada
        for it in self._sched_items:
            if it.row_grid:
                it.row_grid.Background = SolidColorBrush(
                    self._C_ROW_SEL if it.name == schedule_name else self._C_ROW_NORMAL)

        sched = next((s for s in self._schedules if s.Name == schedule_name), None)
        if not sched:
            self.scvPreview.Content = None
            return

        if schedule_name not in self._data_cache:
            headers, rows = read_schedule(doc, sched)
            self._data_cache[schedule_name] = (headers, rows)
        self._raw_headers, self._raw_rows = self._data_cache[schedule_name]

        # Regras: cache > preset salvo > defaults
        actual_headers = self._raw_headers
        if schedule_name in self._rules_cache:
            self._column_rules = list(self._rules_cache[schedule_name])
            cached_names = {r.Name for r in self._column_rules}
            extra_idx = len(self._column_rules)
            for h in actual_headers:
                if h not in cached_names:
                    self._column_rules.append(ColumnRule(
                        h, action=_smart_action(h), sort_order=str(extra_idx + 1)))
                    extra_idx += 1
        else:
            saved = config_manager.load_preset(doc, schedule_name)
            if saved:
                actual_names = set(actual_headers)
                self._column_rules = [
                    ColumnRule.from_rule_dict(r) for r in saved
                    if r.get('name') in actual_names
                ]
                saved_names = {r.Name for r in self._column_rules}
                extra_idx = len(self._column_rules)
                for h in actual_headers:
                    if h not in saved_names:
                        self._column_rules.append(ColumnRule(
                            h, action=_smart_action(h), sort_order=str(extra_idx + 1)))
                        extra_idx += 1
            else:
                self._column_rules = [
                    ColumnRule(h, action=_smart_action(h), sort_order=str(i + 1))
                    for i, h in enumerate(actual_headers)
                ]

        # Aplicar regras por nome se "Mesmas regras para todos" estiver ativo
        if (self.chkSameRules.IsChecked == True and
                self._same_rules_source and
                self._same_rules_source != schedule_name):
            src_rules = self._rules_cache.get(self._same_rules_source) or []
            if src_rules:
                self._column_rules = _remap_rules_by_name(src_rules, self._column_rules)

        self.lblPreviewTitle.Text = 'PREVIEW — {}'.format(schedule_name)
        sched_item = next((it for it in self._sched_items if it.name == schedule_name), None)
        if sched_item:
            self.chkPreviewHeader.IsChecked = sched_item.include_header
            self.chkPreviewHeader.IsEnabled = True
        self._modelo_updating = True
        self.chkModeloSource.IsEnabled = (self.chkSameRules.IsChecked == True)
        self.chkModeloSource.IsChecked = (schedule_name == self._same_rules_source)
        self._modelo_updating = False
        self._refresh_preview()

    def _refresh_preview(self):
        if self._preview_refreshing or not self._raw_headers:
            return
        self._preview_refreshing = True
        try:
            # Propagar mudancas do modelo para schedules ja em cache
            if (self.chkSameRules.IsChecked == True and
                    self._same_rules_source and
                    self._same_rules_source == self._current_name):
                src = list(self._column_rules)
                for name, cached in list(self._rules_cache.items()):
                    if name != self._current_name and cached:
                        self._rules_cache[name] = _remap_rules_by_name(src, cached)

            rule_dicts = [r.to_rule_dict() for r in self._column_rules]
            filtered_rows = apply_filters(self._raw_headers, self._raw_rows, rule_dicts)
            sample = filtered_rows[:200] if len(filtered_rows) > 200 else filtered_rows
            out_headers, grouped_rows = apply_grouping(self._raw_headers, sample, rule_dicts)
            if len(filtered_rows) != len(self._raw_rows):
                self.txtStatusAdv.Text = 'Filtro ativo: {} de {} linhas.'.format(
                    len(filtered_rows), len(self._raw_rows))
            preview_rows = _unique_preview_rows(grouped_rows, 5)

            # Construir full_preview: linhas alinhadas a self._column_rules (Ignorar = '')
            out_idx = {h: i for i, h in enumerate(out_headers)}
            full_preview = []
            for row in preview_rows:
                full_row = []
                for rule in self._column_rules:
                    oi = out_idx.get(rule.Name)
                    full_row.append(row[oi] if (oi is not None and oi < len(row)) else '')
                full_preview.append(full_row)

            self._rebuild_preview_panel(full_preview)
        finally:
            self._preview_refreshing = False

    def _rebuild_preview_panel(self, preview_rows):
        COL_W   = 130
        _C_SEL  = Color.FromRgb(59, 130, 246)   # azul selecao

        outer    = StackPanel()
        outer.Orientation = WPFOrientation.Horizontal
        col_hdrs = []   # referencias aos Border do cabecalho, para atualizar cor sem rebuild

        def _make_col_select(idx, hdrs):
            def h(s, e):
                mods = Keyboard.Modifiers
                if bool(mods & ModifierKeys.Control):
                    if idx in self._selected_cols:
                        self._selected_cols.discard(idx)
                    else:
                        self._selected_cols.add(idx)
                elif bool(mods & ModifierKeys.Shift) and self._selected_cols:
                    last = max(self._selected_cols)
                    lo, hi = min(idx, last), max(idx, last)
                    for k in range(lo, hi + 1):
                        self._selected_cols.add(k)
                else:
                    # Toggle: clicar na mesma coluna desselecionada deseleciona
                    if self._selected_cols == {idx}:
                        self._selected_cols = set()
                    else:
                        self._selected_cols = {idx}
                for j, bdr in enumerate(hdrs):
                    bdr.Background = SolidColorBrush(
                        _C_SEL if j in self._selected_cols else _C_HDR_BG)
                e.Handled = True
            return h

        def _make_action(r, idx):
            def h(s, e):
                if s.SelectedItem and not self._preview_refreshing:
                    new_action = s.SelectedItem
                    r.Action = new_action
                    if idx in self._selected_cols and len(self._selected_cols) > 1:
                        for sel_i in self._selected_cols:
                            if sel_i != idx and sel_i < len(self._column_rules):
                                self._column_rules[sel_i].Action = new_action
                    self._refresh_preview()
            return h

        def _make_sort_toggle(r, idx, b):
            def h(s, e):
                if r.SortOrder:
                    r.SortOrder = ''
                else:
                    r.SortOrder = self._next_sort_order()
                b.Content = r.SortOrder if r.SortOrder else u'—'
                if idx in self._selected_cols and len(self._selected_cols) > 1:
                    active = bool(r.SortOrder)
                    for sel_i in self._selected_cols:
                        if sel_i != idx and sel_i < len(self._column_rules):
                            sr2 = self._column_rules[sel_i]
                            if active and not sr2.SortOrder:
                                sr2.SortOrder = self._next_sort_order()
                            elif not active and sr2.SortOrder:
                                sr2.SortOrder = ''
                self._refresh_preview()
            return h

        def _make_dir(r, idx, b):
            def h(s, e):
                r.SortDir = u'↓' if r.SortDir == u'↑' else u'↑'
                b.Content = r.SortDir
                if idx in self._selected_cols and len(self._selected_cols) > 1:
                    for sel_i in self._selected_cols:
                        if sel_i != idx and sel_i < len(self._column_rules):
                            self._column_rules[sel_i].SortDir = r.SortDir
                self._refresh_preview()
            return h

        def _make_filter(r):
            def h(s, e):
                self._open_filter_popup(r, s)
            return h

        for i, rule in enumerate(self._column_rules):
            col_sp = StackPanel()
            col_sp.Width = COL_W

            # Header — clicavel para selecao de coluna
            hdr_bdr = Border()
            is_sel = (i in self._selected_cols)
            hdr_bdr.Background = SolidColorBrush(_C_SEL if is_sel else _C_HDR_BG)
            hdr_bdr.Padding    = Thickness(4, 4, 4, 4)
            hdr_tb  = TextBlock()
            hdr_tb.Text       = rule.Name
            hdr_tb.Foreground = SolidColorBrush(_C_HDR_FG)
            hdr_tb.FontWeight = FontWeights.SemiBold
            hdr_tb.FontSize   = 10
            hdr_tb.ToolTip    = u'{}\n\nClique: selecionar | Ctrl+Clique: multi | Shift+Clique: intervalo'.format(rule.Name)
            hdr_bdr.Child = hdr_tb
            col_sp.Children.Add(hdr_bdr)
            col_hdrs.append(hdr_bdr)

            # Controles
            ctrl_bdr = Border()
            ctrl_bdr.Background = SolidColorBrush(_C_CTRL_BG)
            ctrl_bdr.Padding    = Thickness(2, 2, 2, 2)
            ctrl_sp = StackPanel()

            cmb = ComboBox()
            cmb.Margin   = Thickness(0, 0, 0, 2)
            cmb.FontSize = 10
            for a in ColumnRule.ACTIONS:
                cmb.Items.Add(a)
            cmb.SelectedItem = rule.Action
            cmb.SelectionChanged += _make_action(rule, i)
            ctrl_sp.Children.Add(cmb)

            sr = StackPanel()
            sr.Orientation = WPFOrientation.Horizontal

            sobtn = Button()
            sobtn.Content  = rule.SortOrder if rule.SortOrder else u'—'
            sobtn.Width    = 34
            sobtn.FontSize = 10
            sobtn.ToolTip  = 'Clique para incluir/remover da ordenacao'
            sobtn.Click   += _make_sort_toggle(rule, i, sobtn)
            sr.Children.Add(sobtn)

            dbtn = Button()
            dbtn.Content  = rule.SortDir
            dbtn.Width    = 30
            dbtn.FontSize = 10
            dbtn.Margin   = Thickness(2, 0, 0, 0)
            dbtn.ToolTip  = 'Direcao (clique para trocar)'
            dbtn.Click   += _make_dir(rule, i, dbtn)
            sr.Children.Add(dbtn)

            fbtn = Button()
            fbtn.Content  = u'▼'
            fbtn.Width    = 24
            fbtn.FontSize = 9
            fbtn.Margin   = Thickness(2, 0, 0, 0)
            if rule.FilterExcluded:
                fbtn.Background = SolidColorBrush(_C_SEL)
                fbtn.Foreground = SolidColorBrush(Color.FromRgb(255, 255, 255))
                fbtn.ToolTip    = 'Filtro ativo: {} valor(es) oculto(s). Clique para editar.'.format(
                    len(rule.FilterExcluded))
            else:
                fbtn.ToolTip = 'Filtrar valores da coluna (estilo Excel)'
            fbtn.Click += _make_filter(rule)
            sr.Children.Add(fbtn)

            ctrl_sp.Children.Add(sr)
            ctrl_bdr.Child = ctrl_sp
            col_sp.Children.Add(ctrl_bdr)

            sep = Border()
            sep.Height     = 1
            sep.Background = SolidColorBrush(_C_SEP)
            col_sp.Children.Add(sep)

            is_ignored = (rule.Action == 'Ignorar')
            for ri, row in enumerate(preview_rows):
                val = str(row[i]) if (not is_ignored and i < len(row)) else ''
                cell_tb = TextBlock()
                cell_tb.FontSize = 10
                cell_tb.Margin   = Thickness(4, 2, 4, 2)
                cell_tb.Text     = val
                cell_tb.ToolTip  = val
                if is_ignored or ri % 2 == 1:
                    cell_bdr = Border()
                    cell_bdr.Background = SolidColorBrush(
                        Color.FromRgb(243, 244, 246) if is_ignored else _C_ALT_BG)
                    cell_bdr.Child = cell_tb
                    col_sp.Children.Add(cell_bdr)
                else:
                    col_sp.Children.Add(cell_tb)

            col_border = Border()
            col_border.BorderBrush     = SolidColorBrush(_C_SEP)
            col_border.BorderThickness = Thickness(0, 0, 1, 0)
            col_border.Child = col_sp
            outer.Children.Add(col_border)

        # Wire selecao apos col_hdrs completo
        for i, hdr_bdr in enumerate(col_hdrs):
            hdr_bdr.MouseLeftButtonDown += _make_col_select(i, col_hdrs)

        self.scvPreview.Content = outer

    def _next_sort_order(self):
        used = set()
        for r in self._column_rules:
            if r.SortOrder:
                try:
                    used.add(int(r.SortOrder))
                except ValueError:
                    pass
        i = 1
        while i in used:
            i += 1
        return str(i)

    # -- FILTRO POR VALORES (estilo Excel) ---------------------------------------

    def _open_filter_popup(self, rule, anchor_btn):
        """Popup com checkbox por valor distinto da coluna — filtra linhas antes do agrupamento."""
        if rule.Name not in self._raw_headers:
            return
        col_idx = self._raw_headers.index(rule.Name)

        values = set()
        for row in self._raw_rows:
            values.add(str(row[col_idx]) if col_idx < len(row) else '')

        def _vkey(v):
            try:
                return (0, float(v), '')
            except ValueError:
                return (1, 0.0, v.lower())
        sorted_vals = sorted(values, key=_vkey)

        state   = {v: (v not in rule.FilterExcluded) for v in sorted_vals}
        visible = list(sorted_vals)

        popup = Popup()
        popup.StaysOpen       = False
        popup.PlacementTarget = anchor_btn
        popup.Placement       = PlacementMode.Bottom
        self._filter_popup    = popup

        root_bdr = Border()
        root_bdr.Background      = SolidColorBrush(Color.FromRgb(255, 255, 255))
        root_bdr.BorderBrush     = SolidColorBrush(_C_HDR_BG)
        root_bdr.BorderThickness = Thickness(1, 1, 1, 1)
        root_bdr.Padding         = Thickness(8, 8, 8, 8)

        sp = StackPanel()
        sp.Width = 220

        title = TextBlock()
        title.Text       = rule.Name
        title.FontSize   = 10
        title.FontWeight = FontWeights.SemiBold
        title.Foreground = SolidColorBrush(_C_HDR_BG)
        title.Margin     = Thickness(0, 0, 0, 4)
        sp.Children.Add(title)

        search = TextBox()
        search.Margin   = Thickness(0, 0, 0, 4)
        search.FontSize = 11
        search.ToolTip  = 'Pesquisar valores'
        sp.Children.Add(search)

        chk_all = CheckBox()
        chk_all.Content   = u'(Selecionar Tudo)'
        chk_all.FontSize  = 11
        chk_all.IsChecked = all(state.values())
        chk_all.Margin    = Thickness(0, 0, 0, 2)
        sp.Children.Add(chk_all)

        scv = ScrollViewer()
        scv.MaxHeight = 220
        list_sp = StackPanel()
        scv.Content = list_sp
        sp.Children.Add(scv)

        def _make_val_handler(v):
            def h(s, e):
                state[v] = bool(s.IsChecked)
            return h

        def _rebuild_list():
            list_sp.Children.Clear()
            del visible[:]
            txt = search.Text.strip().lower()
            for v in sorted_vals:
                label = v if v != '' else u'(Vazias)'
                if txt and txt not in label.lower():
                    continue
                visible.append(v)
                cb = CheckBox()
                cb.Content   = label
                cb.FontSize  = 11
                cb.IsChecked = state[v]
                cb.Checked   += _make_val_handler(v)
                cb.Unchecked += _make_val_handler(v)
                list_sp.Children.Add(cb)

        search.TextChanged += lambda s, e: _rebuild_list()

        def _make_all_handler(value):
            def h(s, e):
                for v in visible:
                    state[v] = value
                _rebuild_list()
            return h
        chk_all.Checked   += _make_all_handler(True)
        chk_all.Unchecked += _make_all_handler(False)

        btn_row = StackPanel()
        btn_row.Orientation         = WPFOrientation.Horizontal
        btn_row.HorizontalAlignment = HorizontalAlignment.Right
        btn_row.Margin              = Thickness(0, 8, 0, 0)

        def _on_ok(s, e):
            rule.FilterExcluded = set(v for v in sorted_vals if not state[v])
            popup.IsOpen = False
            self._refresh_preview()

        def _on_cancel(s, e):
            popup.IsOpen = False

        ok_btn = Button()
        ok_btn.Content  = 'OK'
        ok_btn.Width    = 60
        ok_btn.FontSize = 11
        ok_btn.Click   += _on_ok
        btn_row.Children.Add(ok_btn)

        cancel_btn = Button()
        cancel_btn.Content  = 'Cancelar'
        cancel_btn.Width    = 60
        cancel_btn.FontSize = 11
        cancel_btn.Margin   = Thickness(4, 0, 0, 0)
        cancel_btn.Click   += _on_cancel
        btn_row.Children.Add(cancel_btn)

        sp.Children.Add(btn_row)
        root_bdr.Child = sp
        popup.Child    = root_bdr

        _rebuild_list()
        popup.IsOpen = True

    def _on_preview_header_changed(self, value):
        if self._current_name:
            item = next((it for it in self._sched_items if it.name == self._current_name), None)
            if item:
                item.include_header = value

    # -- WIRE EVENTS -----------------------------------------------------------

    def _wire_events(self):
        self.chkSelectAll.Checked    += lambda s, e: self._select_all(True)
        self.chkSelectAll.Unchecked  += lambda s, e: self._select_all(False)
        self.btnBrowse.Click         += lambda s, e: self._browse_folder(self.txtFolder)
        self.btnUseModel.Click       += lambda s, e: self._use_model_folder(self.txtFolder)
        self.btnAdvBrowse.Click      += lambda s, e: self._browse_folder(self.txtAdvFolder)
        self.btnExportQuick.Click    += self._on_export_quick
        self.btnExportAdv.Click      += self._on_export_adv
        self.btnSavePreset.Click     += self._on_save_preset
        self.btnExportPreset.Click   += self._on_export_preset
        self.btnImportPreset.Click   += self._on_import_preset
        self.btnSaveGas.Click        += self._on_save_gas
        self.chkAdvSelectAll.Checked   += lambda s, e: self._adv_select_all(True)
        self.chkAdvSelectAll.Unchecked += lambda s, e: self._adv_select_all(False)
        self.chkSameRules.Checked    += self._on_same_rules_changed
        self.chkSameRules.Unchecked  += self._on_same_rules_changed
        self.chkModeloSource.Checked += self._on_modelo_source_changed
        self.chkPreviewHeader.Checked   += lambda s, e: self._on_preview_header_changed(True)
        self.chkPreviewHeader.Unchecked += lambda s, e: self._on_preview_header_changed(False)
        self.btnPreviewFinal.Click   += self._on_preview_final
        self.rdoSeparateTabs.Checked += self._on_output_mode_changed
        self.rdoStackedTab.Checked   += self._on_output_mode_changed
        self.rdoAppendTab.Checked    += self._on_output_mode_changed
        self.txtStackedName.TextChanged += self._on_stacked_name_text_changed

    def _select_all(self, select):
        if select:
            self.lstSchedules.SelectAll()
        else:
            self.lstSchedules.SelectedItems.Clear()

    def _adv_select_all(self, select):
        for item in self._sched_items:
            item.is_checked = select
        prev_name = self._current_name
        self._build_adv_schedule_list()
        # Restaurar preview e highlight apos rebuild
        if prev_name:
            self._load_schedule_preview(prev_name)

    def _browse_folder(self, txt_box):
        folder = forms.pick_folder()
        if folder:
            txt_box.Text = folder

    def _use_model_folder(self, txt_box):
        central = None
        try:
            central = revit.query.get_central_path()
        except Exception:
            pass
        if central:
            txt_box.Text = os.path.dirname(central)
        elif doc.PathName:
            txt_box.Text = os.path.dirname(doc.PathName)
        else:
            forms.alert('Modelo nao foi salvo. Selecione uma pasta manualmente.')

    def _on_adv_schedule_changed(self, sender, e):
        try:
            idx = self.lstAdvSchedules.SelectedIndex
            if 0 <= idx < len(self._sched_items):
                self._load_schedule_preview(self._sched_items[idx].name)
        except Exception as ex:
            self.txtStatusAdv.Text = 'Erro: {}'.format(str(ex))

    def _on_same_rules_changed(self, sender, e):
        if (self.chkSameRules.IsChecked == True) and self._column_rules:
            self._same_rules_source = self._current_name
            src_rules = list(self._column_rules)
            self._rules_cache[self._current_name] = src_rules
            for name in list(self._rules_cache.keys()):
                if name != self._current_name:
                    target = self._rules_cache.get(name)
                    if target:
                        self._rules_cache[name] = _remap_rules_by_name(src_rules, target)
            self._modelo_updating = True
            self.chkModeloSource.IsEnabled = True
            self.chkModeloSource.IsChecked = True
            self._modelo_updating = False
            self._build_adv_schedule_list()
            if self._current_name:
                for it in self._sched_items:
                    if it.row_grid:
                        it.row_grid.Background = SolidColorBrush(
                            self._C_ROW_SEL if it.name == self._current_name else self._C_ROW_NORMAL)
            self.txtStatusAdv.Text = 'Mesmas regras. Modelo: {}'.format(self._current_name or '?')
            self._update_stacked_name_preview()
        else:
            self._same_rules_source = None
            self._modelo_updating = True
            self.chkModeloSource.IsEnabled = False
            self.chkModeloSource.IsChecked = False
            self._modelo_updating = False
            self._build_adv_schedule_list()
            if self._current_name:
                for it in self._sched_items:
                    if it.row_grid:
                        it.row_grid.Background = SolidColorBrush(
                            self._C_ROW_SEL if it.name == self._current_name else self._C_ROW_NORMAL)
            self.txtStatusAdv.Text = 'Mesmas regras desativado.'

    def _on_modelo_source_changed(self, sender, e):
        if self._modelo_updating or self.chkModeloSource.IsChecked != True:
            return
        if not self._current_name or not self._column_rules:
            self._modelo_updating = True
            self.chkModeloSource.IsChecked = False
            self._modelo_updating = False
            return
        self._same_rules_source = self._current_name
        self._rules_cache[self._current_name] = list(self._column_rules)
        src_rules = list(self._column_rules)
        for name in list(self._rules_cache.keys()):
            if name != self._current_name:
                target = self._rules_cache.get(name)
                if target:
                    self._rules_cache[name] = _remap_rules_by_name(src_rules, target)
        self._build_adv_schedule_list()
        for it in self._sched_items:
            if it.row_grid:
                it.row_grid.Background = SolidColorBrush(
                    self._C_ROW_SEL if it.name == self._current_name else self._C_ROW_NORMAL)
        self.txtStatusAdv.Text = 'Modelo de regras: {}'.format(self._current_name)
        self._update_stacked_name_preview()

    def _on_preview_final(self, sender, e):
        checked = [it for it in self._sched_items if it.is_checked]
        if not checked:
            self.txtStatusAdv.Text = 'Nenhum schedule marcado para Preview Final.'
            return
        stacked_rows = []
        for idx, item in enumerate(checked):
            if idx > 0:
                stacked_rows.append(('sep', []))
            rules_list = self._rules_cache.get(item.name)
            if item.name not in self._data_cache:
                h_i, r_i = read_schedule(doc, item.schedule)
                self._data_cache[item.name] = (h_i, r_i)
            else:
                h_i, r_i = self._data_cache[item.name]
            if rules_list is None:
                rules_list = [ColumnRule(h, action=_smart_action(h), sort_order=str(j + 1))
                              for j, h in enumerate(h_i)]
            rule_dicts_i = [r.to_rule_dict() for r in rules_list]
            filtered_i   = apply_filters(h_i, r_i, rule_dicts_i)
            sample_r = filtered_i[:200] if len(filtered_i) > 200 else filtered_i
            out_h, out_rows = apply_grouping(h_i, sample_r, rule_dicts_i)
            stacked_rows.append(('title', [item.name]))
            if item.include_header:
                stacked_rows.append(('header', out_h))
            for row in out_rows[:4]:
                stacked_rows.append(('data', row))
            if len(out_rows) > 4:
                stacked_rows.append(('more', ['... ({} grupos total)'.format(len(out_rows))]))
        self._render_stacked_preview(stacked_rows)
        self.lblPreviewTitle.Text = 'PREVIEW FINAL — {} schedule(s)'.format(len(checked))

    def _render_stacked_preview(self, stacked_rows):
        COL_W = 120
        outer = StackPanel()
        outer.Orientation = WPFOrientation.Vertical
        for tag, cells in stacked_rows:
            if tag == 'sep':
                sp_sep = Border()
                sp_sep.Height = 8
                outer.Children.Add(sp_sep)
                continue
            if tag == 'title':
                tb = TextBlock()
                tb.Text       = cells[0] if cells else ''
                tb.FontSize   = 10
                tb.FontWeight = FontWeights.SemiBold
                tb.Foreground = SolidColorBrush(_C_HDR_BG)
                tb.Margin     = Thickness(2, 4, 2, 2)
                outer.Children.Add(tb)
                continue
            is_header = (tag == 'header')
            is_more   = (tag == 'more')
            row_sp = StackPanel()
            row_sp.Orientation = WPFOrientation.Horizontal
            bg = _C_HDR_BG if is_header else (Color.FromRgb(248, 250, 252) if is_more else Color.FromRgb(255, 255, 255))
            fg = _C_HDR_FG if is_header else Color.FromRgb(100, 116, 139)
            fw = FontWeights.SemiBold if is_header else FontWeights.Normal
            for val in cells:
                cell_bdr = Border()
                cell_bdr.Width            = COL_W
                cell_bdr.BorderBrush      = SolidColorBrush(_C_SEP)
                cell_bdr.BorderThickness  = Thickness(0, 0, 1, 1)
                cell_bdr.Background       = SolidColorBrush(bg)
                cell_bdr.Padding          = Thickness(4, 2, 4, 2)
                cell_tb = TextBlock()
                cell_tb.Text       = str(val)
                cell_tb.FontSize   = 10
                cell_tb.FontWeight = fw
                cell_tb.Foreground = SolidColorBrush(fg)
                cell_tb.ToolTip    = str(val)
                cell_bdr.Child = cell_tb
                row_sp.Children.Add(cell_bdr)
            outer.Children.Add(row_sp)
        self.scvPreview.Content = outer

    # -- QUICK EXPORT ----------------------------------------------------------

    def _on_export_quick(self, sender, e):
        selected_names = [str(x) for x in self.lstSchedules.SelectedItems]
        if not selected_names:
            forms.alert('Selecione ao menos um schedule.')
            return

        folder = self.txtFolder.Text.strip()
        if not folder or not os.path.exists(folder):
            forms.alert('Pasta de destino invalida ou nao existe.')
            return

        fmt           = 'excel' if self.rdoExcel.IsChecked else ('gas' if self.rdoGas.IsChecked else 'csv')
        inc_headers   = bool(self.chkHeaders.IsChecked)
        separate      = bool(self.chkSeparateFiles.IsChecked)
        template      = self.cmbFilename.Text.strip() or '{projeto}_{schedule}'

        self.txtStatusQuick.Text = 'Exportando...'
        try:
            schedules_data = self._build_schedules_data(selected_names, inc_headers)
            config_manager.save_config(doc, {
                'default_folder': folder, 'default_format': fmt,
                'include_headers': inc_headers, 'filename_template': template,
            })

            if fmt == 'gas':
                cfg             = config_manager.load_config(doc)
                spreadsheet_url = cfg.get('spreadsheet_url', '').strip()
                if not spreadsheet_url:
                    raise ValueError('URL da planilha Google Sheets nao configurada. Configure em Advanced Export > Google Sheets.')
                gas_client.post_to_gas(spreadsheet_url, schedules_data, doc.Title or '', mode='separate')
                self.txtStatusQuick.Text = 'Enviado ao Google Sheets: {} schedule(s).'.format(len(schedules_data))
                forms.alert('Dados enviados!\n{} schedule(s) exportado(s).'.format(len(schedules_data)))
                return

            if separate and len(schedules_data) > 1:
                exported = []
                for s in schedules_data:
                    fp = self._build_file_path(folder, template, [s['name']], fmt)
                    self._run_export([s], fp, fmt, stacked=False)
                    exported.append(os.path.basename(fp))
                self.txtStatusQuick.Text = 'Exportados: {} arquivos'.format(len(exported))
                forms.alert('Exportacao concluida!\n{} arquivos:\n{}'.format(
                    len(exported), '\n'.join(exported)))
            else:
                fp = self._build_file_path(folder, template, selected_names, fmt)
                self._run_export(schedules_data, fp, fmt, stacked=False)
                self.txtStatusQuick.Text = 'Exportado: {}'.format(os.path.basename(fp))
                forms.alert('Exportacao concluida!\n\n{}'.format(fp))

        except Exception as ex:
            self.txtStatusQuick.Text = 'Erro: {}'.format(str(ex))
            forms.alert('Erro na exportacao:\n{}'.format(str(ex)))

    # -- ADVANCED EXPORT -------------------------------------------------------

    def _on_export_adv(self, sender, e):
        checked = [item for item in self._sched_items if item.is_checked]
        if not checked:
            forms.alert('Selecione ao menos um schedule na lista.')
            return

        # Salvar estado atual no cache
        if self._current_name:
            self._rules_cache[self._current_name] = list(self._column_rules)

        fmt     = 'excel' if self.rdoAdvExcel.IsChecked == True else ('gas' if self.rdoAdvGas.IsChecked == True else 'csv')
        stacked = (self.rdoStackedTab.IsChecked == True)
        append  = (self.rdoAppendTab.IsChecked  == True)
        folder  = self.txtAdvFolder.Text.strip()
        stacked_name_input = self.txtStackedName.Text.strip()
        append_tab_name    = self.txtAppendTabName.Text.strip()

        if append:
            if fmt != 'gas':
                forms.alert('O modo "Acrescentar a aba existente" funciona apenas com Google Sheets.\n'
                            'Selecione o formato Google Sheets.')
                return
            if not append_tab_name:
                forms.alert('Digite o nome exato da aba no Google Sheets onde os dados serao inseridos.')
                return

        if fmt != 'gas' and (not folder or not os.path.exists(folder)):
            forms.alert('Pasta de destino invalida.')
            return

        self.txtStatusAdv.Text = 'Processando...'

        try:
            schedules_data = []
            for item in checked:
                sched      = item.schedule
                rules_list = self._rules_cache.get(item.name)
                headers, rows = read_schedule(doc, sched)

                if rules_list is None:
                    dst_defaults = [
                        ColumnRule(h, action=_smart_action(h), sort_order=str(k + 1))
                        for k, h in enumerate(headers)
                    ]
                    if (self.chkSameRules.IsChecked == True and
                            self._same_rules_source and
                            item.name != self._same_rules_source):
                        src = self._rules_cache.get(self._same_rules_source, [])
                        rules_list = _remap_rules_by_name(src, dst_defaults) if src else dst_defaults
                    else:
                        rules_list = dst_defaults

                rule_dicts            = [r.to_rule_dict() for r in rules_list]
                filtered_rows         = apply_filters(headers, rows, rule_dicts)
                out_headers, out_rows = apply_grouping(headers, filtered_rows, rule_dicts)
                schedules_data.append({
                    'name':           item.name,
                    'headers':        out_headers,
                    'rows':           out_rows,
                    'include_header': item.include_header,
                })

            # Calcular nome da aba stacked: campo > modelo+Merge > fallback
            stacked_name = stacked_name_input
            if not stacked_name and self._same_rules_source:
                stacked_name = self._same_rules_source + '-Merge'
            if not stacked_name:
                stacked_name = 'Dados'

            if fmt == 'gas':
                cfg             = config_manager.load_config(doc)
                spreadsheet_url = cfg.get('spreadsheet_url', '').strip()
                if not spreadsheet_url:
                    raise ValueError('URL da planilha Google Sheets nao configurada. Configure em Advanced Export > Google Sheets.')

                if append:
                    gas_client.post_to_gas(spreadsheet_url, schedules_data, doc.Title or '',
                                           mode='append', tab_name=append_tab_name)
                    self.txtStatusAdv.Text = 'Acrescentado a aba "{}": {} schedule(s).'.format(
                        append_tab_name, len(schedules_data))
                    forms.alert('Dados inseridos na aba "{}"!\n{} schedule(s)'.format(
                        append_tab_name, len(schedules_data)))
                else:
                    mode = 'stacked' if stacked else 'separate'
                    gas_project = stacked_name if stacked else (doc.Title or '')
                    gas_client.post_to_gas(spreadsheet_url, schedules_data, gas_project, mode=mode)
                    self.txtStatusAdv.Text = 'Enviado ao Google Sheets: {} schedule(s).'.format(len(schedules_data))
                    forms.alert('Dados enviados!\n{} schedule(s) | modo: {}'.format(
                        len(schedules_data), 'empilhado' if stacked else 'abas separadas'))
                return

            template = self._cfg.get('filename_template', '{projeto}_{schedule}')

            if not stacked and fmt == 'csv' and len(schedules_data) > 1:
                # CSV "abas separadas" = arquivos separados
                exported = []
                for s in schedules_data:
                    fp = self._build_file_path(folder, template, [s['name']], fmt)
                    self._run_export([s], fp, fmt, stacked=False)
                    exported.append(os.path.basename(fp))
                self.txtStatusAdv.Text = 'Exportados: {} arquivos CSV'.format(len(exported))
                forms.alert('Exportacao concluida!\n{} arquivos:\n{}'.format(
                    len(exported), '\n'.join(exported)))
            else:
                names = [s['name'] for s in schedules_data]
                fp    = self._build_file_path(folder, template, names, fmt)
                self._run_export(schedules_data, fp, fmt, stacked=stacked, tab_name=stacked_name)
                total_rows = sum(len(s['rows']) for s in schedules_data)
                self.txtStatusAdv.Text = 'Exportado: {} ({} grupos)'.format(
                    os.path.basename(fp), total_rows)
                forms.alert('Exportacao concluida!\n{} schedule(s) | {} grupos\n{}'.format(
                    len(schedules_data), total_rows, fp))

        except Exception as ex:
            self.txtStatusAdv.Text = 'Erro: {}'.format(str(ex))
            forms.alert('Erro:\n{}'.format(str(ex)))

    # -- PRESET HANDLERS -------------------------------------------------------

    def _on_save_preset(self, sender, e):
        # Salvar estado atual no cache
        if self._current_name:
            self._rules_cache[self._current_name] = list(self._column_rules)

        # Mesclar com preset existente e salvar
        existing = config_manager.load_project_preset(doc)
        for name, rules in self._rules_cache.items():
            existing[name] = _rules_to_preset(rules)
        config_manager.save_project_preset(doc, existing)
        self.txtStatusAdv.Text = 'Preset do projeto salvo ({} schedule(s)).'.format(len(existing))

    def _on_export_preset(self, sender, e):
        if self._current_name:
            self._rules_cache[self._current_name] = list(self._column_rules)
        path = forms.save_file(file_ext='json', default_name='exportpro_preset.json')
        if not path:
            return
        existing = config_manager.load_project_preset(doc)
        for name, rules in self._rules_cache.items():
            existing[name] = _rules_to_preset(rules)
        config_manager.export_preset_to_file(existing, path)
        self.txtStatusAdv.Text = 'Preset exportado: {}'.format(os.path.basename(path))

    def _on_import_preset(self, sender, e):
        path = forms.pick_file(file_ext='json')
        if not path:
            return
        try:
            imported = config_manager.import_preset_from_file(path)
            for name, rules in imported.items():
                self._rules_cache[name] = [ColumnRule.from_rule_dict(r) for r in rules]
            # Recarregar schedule atual
            if self._current_name and self._current_name in self._rules_cache:
                self._column_rules = list(self._rules_cache[self._current_name])
                sched = next((s for s in self._schedules if s.Name == self._current_name), None)
                if sched:
                    if self._current_name not in self._data_cache:
                        self._raw_headers, self._raw_rows = read_schedule(doc, sched)
                        self._data_cache[self._current_name] = (self._raw_headers, self._raw_rows)
                    else:
                        self._raw_headers, self._raw_rows = self._data_cache[self._current_name]
                    self._refresh_preview()
            count = len(imported)
            self.txtStatusAdv.Text = 'Preset importado: {} schedule(s) de {}'.format(
                count, os.path.basename(path))
        except ValueError as ex:
            forms.alert(str(ex))

    def _on_save_gas(self, sender, e):
        config_manager.save_config(doc, {'spreadsheet_url': self.txtGasUrl.Text.strip()})
        self.txtStatusAdv.Text = 'URL da planilha salva.'

    def _on_output_mode_changed(self, sender, e):
        from System.Windows import Visibility
        is_stacked = (self.rdoStackedTab.IsChecked == True)
        is_append  = (self.rdoAppendTab.IsChecked  == True)
        self.pnlStackedName.Visibility = Visibility.Visible   if is_stacked else Visibility.Collapsed
        self.pnlAppendName.Visibility  = Visibility.Visible   if is_append  else Visibility.Collapsed
        if is_stacked:
            self._update_stacked_name_preview()

    def _on_stacked_name_text_changed(self, sender, e):
        self._update_stacked_name_preview()

    def _update_stacked_name_preview(self):
        text = self.txtStackedName.Text.strip()
        if text:
            preview = text
        elif self._same_rules_source:
            preview = self._same_rules_source + '-Merge'
        else:
            preview = 'Dados'
        self.lblStackedNamePreview.Text = u'→ "{}"'.format(preview)

    # -- HELPERS ---------------------------------------------------------------

    def _build_schedules_data(self, schedule_names, include_headers=True):
        data = []
        for name in schedule_names:
            sched = next((s for s in self._schedules if s.Name == name), None)
            if sched:
                headers, rows = read_schedule(doc, sched)
                data.append({'name': name, 'headers': headers, 'rows': rows,
                             'include_header': include_headers})
        return data

    def _build_file_path(self, folder, template, schedule_names, fmt):
        import re
        project_name = doc.Title or 'Projeto'
        sched_part   = schedule_names[0] if len(schedule_names) == 1 \
                       else 'Batch_{}'.format(len(schedule_names))
        filename = template.format(projeto=project_name, schedule=sched_part)
        filename = re.sub(r'[\\/:*?"<>|]', '_', filename).strip('. ') or 'export'
        ext      = 'xlsx' if fmt == 'excel' else 'csv'
        return os.path.join(folder, '{}.{}'.format(filename, ext))

    def _run_export(self, schedules_data, file_path, fmt, stacked=False, tab_name=None):
        if fmt == 'csv':
            csv_exporter.export_csv(schedules_data, file_path)
        elif fmt == 'excel':
            excel_exporter.export_excel(schedules_data, file_path, stacked=stacked,
                                        tab_name=tab_name)


# -- MAIN ----------------------------------------------------------------------

def main():
    try:
        if not get_all_schedules(doc):
            forms.alert('Nenhum schedule encontrado no modelo.', exitscript=True)
        window = ExportProWindow()
        window.ShowDialog()
    except OperationCanceledException:
        pass
    except Exception as ex:
        output.print_md('**Erro:** {}'.format(str(ex)))
        output.print_md('```\n{}\n```'.format(traceback.format_exc()))


if __name__ == '__main__':
    main()
